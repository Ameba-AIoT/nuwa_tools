import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

NUWA_SDK_VENV_DIR = '.venv'
NUWA_ZEPHYR_REQUIREMENTS = os.path.join('zephyr', 'scripts', 'requirements.txt')
NUWA_TOOLS_REQUIREMENTS = os.path.join('tools', 'requirements.txt')
NUWA_AMEBA_REQUIREMENTS = os.path.join(
    'modules', 'hal', 'realtek', 'ameba', 'scripts', 'requirements.txt'
)

NUWA_SDK_QUERY_CFG_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', 'query.json'
)
NUWA_SDK_TOOLCHAIN_FILE = os.path.join(
    'modules', 'hal', 'realtek', 'ameba', 'scripts', 'toolchain_db.json'
)
NUWA_SDK_TOOLCHAIN_DEFAULT_PATH_WINDOWS = 'C:\\rtk-toolchain'
NUWA_SDK_TOOLCHAIN_DEFAULT_PATH_LINUX = os.path.expanduser('~/rtk-toolchain')


def get_venv_python_executable(venv_dir):
    directory = 'Scripts' if os.name == 'nt' else 'bin'
    executable = 'python.exe' if os.name == 'nt' else 'python'
    return os.path.join(venv_dir, directory, executable)


VENV_PYTHON_EXECUTABLE = get_venv_python_executable(NUWA_SDK_VENV_DIR)


def _venv_env():
    env = os.environ.copy()
    env['PYTHONNOUSERSITE'] = 'True'
    # Propagate venv Python to all child processes (cmake, west, sysbuild
    # sub-images like mcuboot).  cmake's python.cmake searches VIRTUAL_ENV
    # and PATH; without this, sub-cmake invocations pick up /usr/bin/python
    # which may lack pykwalify and other Zephyr deps.
    venv_abs = os.path.abspath(NUWA_SDK_VENV_DIR)
    if os.path.exists(venv_abs):
        bin_dir = 'Scripts' if os.name == 'nt' else 'bin'
        env['VIRTUAL_ENV'] = venv_abs
        env['PATH'] = os.path.join(venv_abs, bin_dir) + os.pathsep + env.get('PATH', '')
    return env


def run_west(args, cwd=None, env=None, check=True, capture_output=False):
    command = [VENV_PYTHON_EXECUTABLE, '-m', 'west'] + list(args)
    merged_env = _venv_env()
    if env:
        merged_env.update(env)
    return subprocess.run(
        command,
        cwd=cwd,
        env=merged_env,
        check=check,
        text=True,
        capture_output=capture_output,
    )


def resolve_toolchain_path(board):
    """Look up the gnuarmemb toolchain for `board`'s chip in toolchain_db.json,
    installing it via `west realtek ameba install` if not present locally.
    Returns the toolchain's linux/newlib (or mingw32/newlib) directory.
    """
    board = board.split('/')[0]

    if not os.path.exists(NUWA_SDK_QUERY_CFG_FILE):
        print('Error: Query configuration file "' + NUWA_SDK_QUERY_CFG_FILE + '" does not exist')
        sys.exit(1)
    with open(NUWA_SDK_QUERY_CFG_FILE, 'r') as f:
        cfg = json.load(f)
    if board not in cfg['devices'].keys():
        print('Error: Unsupported board "' + board + '", valid values: ')
        [print(key) for key in cfg['devices'].keys()]
        sys.exit(1)
    chip = cfg['devices'][board]['chip']

    if not os.path.exists(NUWA_SDK_TOOLCHAIN_FILE):
        print('Error: Toolchain configuration file "' + NUWA_SDK_TOOLCHAIN_FILE + '" does not exist')
        sys.exit(1)
    with open(NUWA_SDK_TOOLCHAIN_FILE, 'r') as f:
        toolchain_db = json.load(f)

    toolchain_id = None
    chip_key = chip.strip().lower()
    for k, v in toolchain_db.items():
        chips = [str(c).strip().lower() for c in v.get('chips', [])] if isinstance(v, dict) else []
        if chip_key in chips:
            toolchain_id = k
            break
    if toolchain_id is None:
        print('Error: Unsupported chip "' + chip + '" (board "' + board + '") in toolchain file "'
              + NUWA_SDK_TOOLCHAIN_FILE + '"')
        sys.exit(1)

    if os.name == 'nt':
        toolchain_dir = Path(NUWA_SDK_TOOLCHAIN_DEFAULT_PATH_WINDOWS)
        toolchain_path = toolchain_dir / toolchain_id / 'mingw32' / 'newlib'
    else:
        toolchain_dir = Path(NUWA_SDK_TOOLCHAIN_DEFAULT_PATH_LINUX)
        toolchain_path = toolchain_dir / toolchain_id / 'linux' / 'newlib'

    if not toolchain_path.exists():
        print(f"Error: Toolchain '{toolchain_path}' does not exist")
        try:
            run_west(["realtek", "ameba", "install", "-t", toolchain_id])
            print("toolchain install successful")
        except subprocess.CalledProcessError:
            print("toolchain install failed")
            sys.exit(1)

    return toolchain_path


def set_toolchain_env(board):
    """Resolve and export ZEPHYR_TOOLCHAIN_VARIANT/GNUARMEMB_TOOLCHAIN_PATH for `board`.

    Always overwrites any pre-existing values in the shell environment, so the
    correct versioned toolchain is used regardless of what the caller's shell
    had set beforehand.
    """
    toolchain_path = resolve_toolchain_path(board)
    os.environ['ZEPHYR_TOOLCHAIN_VARIANT'] = 'gnuarmemb'
    os.environ['GNUARMEMB_TOOLCHAIN_PATH'] = str(toolchain_path)
    return toolchain_path


def _file_hash(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        h.update(f.read())
    return h.hexdigest()


def _sentinel_path(name):
    return os.path.join(NUWA_SDK_VENV_DIR, name)


def _deps_up_to_date(requirements_file, sentinel_name):
    if not os.path.exists(requirements_file):
        return False
    sentinel = _sentinel_path(sentinel_name)
    if not os.path.exists(sentinel):
        return False
    try:
        with open(sentinel, 'r') as f:
            return f.read().strip() == _file_hash(requirements_file)
    except Exception:
        return False


def _mark_deps_installed(requirements_file, sentinel_name):
    sentinel = _sentinel_path(sentinel_name)
    with open(sentinel, 'w') as f:
        f.write(_file_hash(requirements_file))


def _venv_has_pip():
    try:
        subprocess.check_call(
            [VENV_PYTHON_EXECUTABLE, '-m', 'pip', '--version'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return True
    except Exception:
        return False


def _venv_has_module(module_name):
    try:
        subprocess.check_call(
            [VENV_PYTHON_EXECUTABLE, '-c', 'import ' + module_name],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return True
    except Exception:
        return False


def check_venv():
    print("Check Python virtual environment...")
    if os.path.exists(NUWA_SDK_VENV_DIR):
        print("Python virtual environment exists")
    else:
        # Create virtual environment if it does not exist
        try:
            print("Python virtual environment does not exist")
            if sys.platform == "win32":
                # Check if virtualenv is installed by trying to import it
                try:
                    import virtualenv
                except ImportError:
                    print("virtualenv is not installed. Installing it...")
                    try:
                        subprocess.check_call(
                            [sys.executable, "-m", "pip", "install", "virtualenv"],
                        )
                    except Exception as e:
                        print("Error: Failed to install virtualenv:", e)
                        sys.exit(2)
                subprocess.check_call([sys.executable, '-m', 'virtualenv', NUWA_SDK_VENV_DIR])
            else:
                import venv
                venv.create(NUWA_SDK_VENV_DIR, with_pip=True)
            print("Python virtual environment created")
        except Exception as e:
            print("Error: Failed to create Python virtual environment:", e)
            sys.exit(2)

    env = os.environ.copy()
    env['PYTHONNOUSERSITE'] = 'True'

    # Ensure pip is available
    if _venv_has_pip():
        print("pip is available.")
    else:
        try:
            print("Installing pip in virtual environment...")
            subprocess.check_call(
                [VENV_PYTHON_EXECUTABLE, '-m', 'ensurepip'],
                env=env
            )
            print("pip installed successfully.")
        except Exception as e:
            print("Warning: ensurepip failed or is not available. Error:", e)
            sys.exit(2)

    # Install 'west' only if not already present
    if _venv_has_module('west'):
        print("Package 'west' is available.")
    else:
        try:
            print("Installing package 'west'...")
            subprocess.check_call(
                [VENV_PYTHON_EXECUTABLE, '-m', 'pip', 'install', 'west'],
                env=env
            )
            print("Package 'west' installed successfully.")
        except Exception as e:
            print("Error: Failed to install package 'west'.", e)
            sys.exit(2)

    # Install Zephyr Python dependencies
    if os.path.exists(NUWA_ZEPHYR_REQUIREMENTS):
        if _deps_up_to_date(NUWA_ZEPHYR_REQUIREMENTS, '.zephyr_deps_hash'):
            print("Zephyr Python dependencies up to date, skipping.")
        else:
            try:
                print("Installing Zephyr Python dependencies (this may take a while)...")
                subprocess.check_call(
                    [VENV_PYTHON_EXECUTABLE, '-m', 'pip', 'install', '-r', NUWA_ZEPHYR_REQUIREMENTS],
                    env=env
                )
                _mark_deps_installed(NUWA_ZEPHYR_REQUIREMENTS, '.zephyr_deps_hash')
                print("Zephyr Python dependencies installed successfully.")
            except Exception as e:
                print("Error: Failed to install Zephyr Python dependencies.", e)
                sys.exit(2)

    # Install Realtek tools Python dependencies
    if os.path.exists(NUWA_TOOLS_REQUIREMENTS):
        if _deps_up_to_date(NUWA_TOOLS_REQUIREMENTS, '.tools_deps_hash'):
            print("Realtek tools Python dependencies up to date, skipping.")
        else:
            try:
                print("Installing Realtek tools Python dependencies...")
                subprocess.check_call(
                    [VENV_PYTHON_EXECUTABLE, '-m', 'pip', 'install', '-r', NUWA_TOOLS_REQUIREMENTS],
                    env=env
                )
                _mark_deps_installed(NUWA_TOOLS_REQUIREMENTS, '.tools_deps_hash')
                print("Realtek tools Python dependencies installed successfully.")
            except Exception as e:
                print("Error: Failed to install Realtek tools Python dependencies.", e)
                sys.exit(2)

    # Install Ameba image-tool Python dependencies
    if os.path.exists(NUWA_AMEBA_REQUIREMENTS):
        if _deps_up_to_date(NUWA_AMEBA_REQUIREMENTS, '.ameba_deps_hash'):
            print("Ameba image-tool Python dependencies up to date, skipping.")
        else:
            try:
                print("Installing Ameba image-tool Python dependencies...")
                subprocess.check_call(
                    [VENV_PYTHON_EXECUTABLE, '-m', 'pip', 'install', '-r', NUWA_AMEBA_REQUIREMENTS],
                    env=env
                )
                _mark_deps_installed(NUWA_AMEBA_REQUIREMENTS, '.ameba_deps_hash')
                print("Ameba image-tool Python dependencies installed successfully.")
            except Exception as e:
                print("Error: Failed to install Ameba image-tool Python dependencies.", e)
                sys.exit(2)
