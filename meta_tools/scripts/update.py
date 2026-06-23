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

NUWA_SDK_GIT_HOOKS_DIR = 'tools/meta_tools/git_hooks'

def update_git_hooks():
    result = utils.run_west(['list', '--format', '{path}'], capture_output=True, check=False)
    if result.returncode != 0:
        print("Error: Fail to get west repo list, please check the west environment")
        sys.exit(2)

    for repo in result.stdout.strip().split('\n'):
        if not repo:
            continue
        target_dir = os.path.join(repo, '.git', 'hooks')
        if os.path.exists(target_dir):
            hooks = glob.glob(NUWA_SDK_GIT_HOOKS_DIR + "/*")
            for hook in hooks:
                if os.path.isdir(hook):
                    pass
                elif os.path.isfile(hook):
                    shutil.copy(hook, target_dir)
                    os.chmod(os.path.join(target_dir, os.path.basename(hook)), 0o755)
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
        try:
            utils.run_west(["forall", "-c", "git reset --hard && git clean -fd"])
        except subprocess.CalledProcessError as e:
            print("Error: Failed to clean workspace:", e)
            sys.exit(1)
        print("Clean workspace done")

    print("Update manifest...")
    subprocess.run(["git", "pull"], cwd="manifests", check=True, text=True)
    print("Update manifest done")

    print("Update workspace...")
    utils.run_west(["update", "-k", "-r"])
    print("Update workspace done")

    print("Update Git hooks...")
    update_git_hooks()
    print("Update Git hooks done")

    print("Update done")

if __name__ == '__main__':
    main(len(sys.argv), sys.argv[1:])
