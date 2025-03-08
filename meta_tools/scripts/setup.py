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
import venv

NUWA_SDK_VENV_DIR = '.venv'
NUWA_SDK_ZEPHYR_REQUIREMENTS_PATH = 'zephyr/scripts/requirements.txt'
NUWA_SDK_NUWA_REQUIREMENTS_PATH = 'tools/requirements.txt'
NUWA_SDK_GIT_HOOKS_DIR = 'tools/meta_tools/git_hooks'

CMD_WEST_UPDATE = 'west update'
CMD_WEST_LIST = "west list | awk '{print $2}'"
CMD_INSTALL_ZEPHYR_REQUIREMENTS = 'pip install -r ' + NUWA_SDK_ZEPHYR_REQUIREMENTS_PATH
CMD_INSTALL_NUWA_REQUIREMENTS = 'pip install -r ' + NUWA_SDK_NUWA_REQUIREMENTS_PATH
CMD_CLEAN_WORKSPACE = "west forall -c 'git reset --hard && git clean -fd'"

def check_venv():
    print("Check Python virtual environment...")
    if os.path.exists(NUWA_SDK_VENV_DIR):
        print("Python virtual environment exists")
    else:
        # Create virtual environment if it does not exist
        try:
            print("Python virtual environment does not exist")
            venv.create(NUWA_SDK_VENV_DIR)
            print("Python virtual environment created")
        except:
            print("Error: Fail to create Python virtual environment")
            sys.exit(2)

def run_shell_cmd_with_output(cmd):
    return subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

def update_git_hooks():
    repo_list = run_shell_cmd_with_output(CMD_WEST_LIST)
    if repo_list.returncode != 0:
        print("Error: Fail to get west repo list, please check the west environment")
        sys.exit(2)
    else:
        pass

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
            sys.exit(2)

def main(argc, argv):
    parser = argparse.ArgumentParser(description=None)
    parser.add_argument('-g', '--update-git-hooks', action='store_true', help='update git hooks')
    parser.add_argument('-p', '--pristine', action='store_true', help='pristine build')

    args = parser.parse_args()

    print("Set up...")

    if args.pristine:
        print("Clean workspace...")
        os.system(CMD_CLEAN_WORKSPACE)
        print("Clean workspace done")
    else:
        pass

    # Check virtual environment
    check_venv()
    
    cmd = ''
    cmd_activate_venv = None
    cmd_deactivate_venv = None
    if os.name == 'nt':
        cmd_activate_venv = os.path.join(NUWA_SDK_VENV_DIR, 'Scripts', 'activate.bat')
        cmd_deactivate_venv = os.path.join(NUWA_SDK_VENV_DIR, 'Scripts', 'deactivate.bat')
    else:
        cmd_activate_venv = 'source ' + os.path.join(NUWA_SDK_VENV_DIR, 'bin', 'activate')
        cmd_deactivate_venv = 'deactivate'
    
    cmd += cmd_activate_venv + ' && '
    cmd += 'echo "Update workspace..." && ' + CMD_WEST_UPDATE + ' && echo "Update workspace done" && '
    cmd += 'echo "Install Zephyr requirements..." && ' + CMD_INSTALL_ZEPHYR_REQUIREMENTS + ' && echo "Install Zephyr requirements done" && '
    cmd += 'echo "Install Nuwa requirements..." && ' + CMD_INSTALL_NUWA_REQUIREMENTS + ' && echo "Install Nuwa requirements done"'

    rc = 0
    try:
        rc = os.system(cmd)
    except:
        run_shell_cmd_with_output(cmd_deactivate_venv)
        print("Error: Set up Nuwa SDK failed")
        sys.exit(2)

    run_shell_cmd_with_output(cmd_deactivate_venv)

    if rc != 0:
        print("Error: Set up Nuwa SDK failed (" + str(rc) + ")")
        sys.exit(2)
    else:
        pass

    if args.update_git_hooks:
        print("Update Git hooks...")
        update_git_hooks()
        print("Update Git hooks done")
    else:
        pass

    print("Set up Nuwa SDK done")

if __name__ == '__main__':
    main(len(sys.argv), sys.argv[1:])
