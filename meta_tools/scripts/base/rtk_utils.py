import hashlib
import os
import subprocess
import sys

NUWA_SDK_VENV_DIR = '.venv'
NUWA_ZEPHYR_REQUIREMENTS = os.path.join('zephyr', 'scripts', 'requirements.txt')
NUWA_TOOLS_REQUIREMENTS = os.path.join('tools', 'requirements.txt')


def get_venv_python_executable(venv_dir):
    directory = 'Scripts' if os.name == 'nt' else 'bin'
    executable = 'python.exe' if os.name == 'nt' else 'python'
    return os.path.join(venv_dir, directory, executable)


VENV_PYTHON_EXECUTABLE = get_venv_python_executable(NUWA_SDK_VENV_DIR)


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
