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

NUWA_SDK_GIT_HOOKS_DIR = 'tools/meta_tools/git_hooks'

CMD_CLEAN_WORKSPACE = "west forall -c 'git reset --hard && git clean -fd'"
CMD_UPDATE_MANIFEST = 'cd manifests && git pull && cd -'
CMD_WEST_UPDATE = 'west update'
CMD_WEST_LIST = "west list | awk '{print $2}'"

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
    parser.add_argument('-p', '--pristine', action='store_true', help='pristine build')

    args = parser.parse_args()

    print("Update...")

    if args.pristine:
        print("Clean workspace...")
        os.system(CMD_CLEAN_WORKSPACE)
        print("Clean workspace done")
    else:
        pass

    print("Update manifest...")
    os.system(CMD_UPDATE_MANIFEST)
    print("Update manifest done")

    print("Update workspace...")
    os.system(CMD_WEST_UPDATE)
    print("Update workspace done")

    print("Update Git hooks...")
    update_git_hooks()
    print("Update Git hooks done")

    print("Update done")

if __name__ == '__main__':
    main(len(sys.argv), sys.argv[1:])
