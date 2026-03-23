#! /usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (c) 2024 Realtek Semiconductor Corp.
# SPDX-License-Identifier: Apache-2.0

import argparse
import glob
import os
import shutil
import subprocess
import sys

import base.rtk_utils as utils

NUWA_SDK_ZEPHYR_REQUIREMENTS_PATH = 'zephyr/scripts/requirements.txt'
NUWA_SDK_NUWA_REQUIREMENTS_PATH = 'tools/requirements.txt'
NUWA_SDK_GIT_HOOKS_DIR = 'tools/meta_tools/git_hooks'

CMD_WEST_UPDATE = f"{utils.VENV_PYTHON_EXECUTABLE} -m west update"
CMD_WEST_LIST = f"{utils.VENV_PYTHON_EXECUTABLE} -m west list | awk '{{print $2}}'"
CMD_CLEAN_WORKSPACE = f"{utils.VENV_PYTHON_EXECUTABLE} -m west forall -c 'git reset --hard && git clean -fd'"


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

def install_requirements(executable, requirements_path, label, env):
    print(f"Install {label} requirements...")
    try:
        subprocess.run([executable, "-m", "pip", "install", "-r", requirements_path],
                       env=env, check=True)
        print(f"Install {label} requirements done")
    except subprocess.CalledProcessError as e:
        print(f"Error: Install {label} requirements failed ({e.returncode})")
        print("Set up Nuwa SDK failed")
        sys.exit(2)

def install_zephyr_deps_via_west(venv_python, env):
    print("Install Zephyr requirements via 'west packages pip --install'...")
    try:
        subprocess.run([
            venv_python, "-m", "west", "packages", "pip", "--install"
        ], env=env, check=True)
        print("Install Zephyr requirements via west done")
    except subprocess.CalledProcessError as e:
        print(f"Error: Install Zephyr requirements via 'west packages pip --install' failed ({e.returncode})")
        print("Set up Nuwa SDK failed")
        sys.exit(2)

def main(argc, argv):
    parser = argparse.ArgumentParser(description=None)
    parser.add_argument('-g', '--update-git-hooks', action='store_true', help='update git hooks')
    parser.add_argument('-p', '--pristine', action='store_true', help='pristine build')

    args = parser.parse_args()

    print("Set up...")

    if args.pristine and os.path.exists(".venv"):
        print("Remove existing .venv folder...")
        shutil.rmtree(".venv")

    utils.check_venv()

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

    env = os.environ.copy()
    env['PYTHONNOUSERSITE'] = 'True'

    print("Upgrading pip in virtual environment...")
    try:
        subprocess.run([utils.VENV_PYTHON_EXECUTABLE, "-m", "pip", "install", "--upgrade", "pip"],
                       env=env, check=True, stdout=subprocess.DEVNULL)
        print("pip upgraded successfully")
    except subprocess.CalledProcessError as e:
        print(f"Warning: Failed to upgrade pip (return code {e.returncode}), proceeding anyway...")

    # install_requirements(utils.VENV_PYTHON_EXECUTABLE,
    #                      NUWA_SDK_ZEPHYR_REQUIREMENTS_PATH,
    #                      "Zephyr", env)
    install_zephyr_deps_via_west(utils.VENV_PYTHON_EXECUTABLE, env)

    install_requirements(utils.VENV_PYTHON_EXECUTABLE,
                         NUWA_SDK_NUWA_REQUIREMENTS_PATH,
                         "Nuwa", env)

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
