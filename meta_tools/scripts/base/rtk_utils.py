import os
import subprocess
import sys

NUWA_SDK_VENV_DIR = '.venv'


def get_venv_python_executable(venv_dir):
    directory = 'Scripts' if os.name == 'nt' else 'bin'
    executable = 'python.exe' if os.name == 'nt' else 'python'
    return os.path.join(venv_dir, directory, executable)


VENV_PYTHON_EXECUTABLE = get_venv_python_executable(NUWA_SDK_VENV_DIR)


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
                        # Install virtualenv silently
                        subprocess.check_call(
                            [sys.executable, "-m", "pip", "install", "virtualenv"],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
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
    # install pip and west if possible
    env = os.environ.copy()
    env['PYTHONNOUSERSITE'] = 'True'

    try:
        subprocess.check_call([VENV_PYTHON_EXECUTABLE, '-m', 'ensurepip'], stdout=subprocess.DEVNULL, env=env)
        print("ensurepip executed successfully.")
    except Exception as e:
        # If ensurepip is not present (which may occur in a Python embed distribution)
        # we assume that pip might have been already installed.
        print("Warning: ensurepip failed or is not available. Error:", e)
        # Optionally, verify that pip is available. For example:
        try:
            subprocess.check_call([VENV_PYTHON_EXECUTABLE, '-m', 'pip', '--version'], stdout=subprocess.DEVNULL,
                                  env=env)
            print("pip appears to be available.")
        except Exception as pip_err:
            print("Error: pip does not seem to be installed and ensurepip failed. Exiting.", pip_err)
            sys.exit(2)

    # Install 'west' via pip. This installation is attempted regardless.
    try:
        subprocess.check_call([VENV_PYTHON_EXECUTABLE, '-m', 'pip', 'install', 'west'], stdout=subprocess.DEVNULL,
                              env=env)
        print("Package 'west' installed successfully.")
    except Exception as e:
        print("Error: Failed to install package 'west'.", e)
        sys.exit(2)
