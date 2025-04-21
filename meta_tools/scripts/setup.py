#! /usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (c) 2024 Realtek Semiconductor Corp.
# SPDX-License-Identifier: Apache-2.0 

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
from typing import Dict, List
import venv

NUWA_SDK_VENV_DIR = '.venv'
VENV_PYTHON_EXECUTABLE = os.path.join(NUWA_SDK_VENV_DIR, 'bin', 'python')
NUWA_SDK_ZEPHYR_REQUIREMENTS_PATH = 'zephyr/scripts/requirements.txt'
NUWA_SDK_NUWA_REQUIREMENTS_PATH = 'tools/requirements.txt'
NUWA_SDK_GIT_HOOKS_DIR = 'tools/meta_tools/git_hooks'

CMD_WEST_UPDATE = f"{VENV_PYTHON_EXECUTABLE} -m west update"
CMD_WEST_LIST = f"{VENV_PYTHON_EXECUTABLE} -m west list | awk '{{print $2}}'"
CMD_INSTALL_ZEPHYR_REQUIREMENTS = f"{VENV_PYTHON_EXECUTABLE}  -m pip install -r {NUWA_SDK_ZEPHYR_REQUIREMENTS_PATH}"
CMD_INSTALL_NUWA_REQUIREMENTS = f"{VENV_PYTHON_EXECUTABLE} -m pip install -r {NUWA_SDK_NUWA_REQUIREMENTS_PATH}"
CMD_CLEAN_WORKSPACE = f"{VENV_PYTHON_EXECUTABLE} -m west forall -c 'git reset --hard && git clean -fd'"

def check_venv():
    print("Check Python virtual environment...")
    if os.path.exists(NUWA_SDK_VENV_DIR):
        print("Python virtual environment exists")
    else:
        # Create virtual environment if it does not exist
        try:
            print("Python virtual environment does not exist")
            venv.create(NUWA_SDK_VENV_DIR, with_pip=True)
            print("Python virtual environment created")
        except:
            print("Error: Fail to create Python virtual environment")
            sys.exit(2)
    # install pip and west no matter they exist or not
    env = os.environ.copy()
    env['PYTHONNOUSERSITE'] = 'True'
    python_executable = os.path.join(NUWA_SDK_VENV_DIR, 'bin', 'python')
    subprocess.check_call([python_executable, '-m', 'ensurepip'], env=env)
    subprocess.check_call([python_executable, '-m', 'pip', 'install', 'west'], env=env)
    

def run_shell_cmd_with_output(cmd):
    return subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

def update_git_hooks(cmd):
    rc = 0
    
    try:
        repo_list = run_shell_cmd_with_output(cmd)
        if repo_list.returncode != 0:
            print("Error: Fail to get west repo list, please check the west environment")
            rc = 1
        else:
            for repo in repo_list.stdout.strip().split('\n'):
                target_dir = os.path.join(repo, '.git', 'hooks')
                if os.path.exists(target_dir):
                    hooks = glob.glob(NUWA_SDK_GIT_HOOKS_DIR + "/*")
                    for hook in hooks:
                        if os.path.isdir(hook):
                            pass
                        elif os.path.isfile(hook):
                            shutil.copy(hook, target_dir)
                            os.system("chmod a+x " + os.path.join(target_dir, os.path.basename(hook)))
                        else:
                            pass
                else:
                    print("Error: Repo '" + repo + "' damaged, no .git directory found")
                    rc = 1
                    break
    except:
        rc = 1

    return rc

def run_commands(commands: List[str], env: Dict[str, str]) -> int:
    """Helper function to run multiple shell commands within a session."""
    try:
        with subprocess.Popen(['/bin/bash'], stdin=subprocess.PIPE, env=env, text=True) as proc:
            for cmd in commands:
                proc.stdin.write(cmd + '\n')
            proc.stdin.close()
            rc = proc.wait()
            return rc
    except subprocess.CalledProcessError as e:
        print(f"Error: Command failed with exit code {e.returncode}")
        sys.exit(e.returncode)

def main(argc, argv):
    parser = argparse.ArgumentParser(description=None)
    parser.add_argument('-g', '--update-git-hooks', action='store_true', help='update git hooks')
    parser.add_argument('-p', '--pristine', action='store_true', help='pristine build')

    args = parser.parse_args()

    print("Set up...")

    if args.pristine and os.path.exists(".venv"):
        print("Remove existing .venv folder...")
        shutil.rmtree(".venv")

    check_venv()

    if args.pristine:
        print("Clean workspace...")
        try:
            rc = os.system(CMD_CLEAN_WORKSPACE)
        except:
            print("Error: Clean workspace failed")
            sys.exit(2)
        print("Clean workspace done")
    else:
        pass

    # This list will be execute in a session in order
    commands = [
        'echo "Install Zephyr requirements..."',
        CMD_INSTALL_ZEPHYR_REQUIREMENTS,
        'echo "Install Zephyr requirements done"',
        'echo "Install Nuwa requirements..."',
        CMD_INSTALL_NUWA_REQUIREMENTS,
        'echo "Install Nuwa requirements done"'
    ]

    env = os.environ.copy()
    env['PYTHONNOUSERSITE'] = 'True'
    rc = run_commands(commands, env)

    if rc != 0:
        print("Error: Set up Nuwa SDK failed (" + str(rc) + ")")
        sys.exit(2)
    else:
        pass

    if args.update_git_hooks:
        print("Update Git hooks...")
        rc = update_git_hooks(CMD_WEST_LIST)
        if rc != 0:
            print("Error: Update Git hooks failed (" + str(rc) + ")")
            sys.exit(2)
        else:
            print("Update Git hooks done")
    else:
        pass

    print("Set up Nuwa SDK done")

if __name__ == '__main__':
    main(len(sys.argv), sys.argv[1:])
