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

def _run_west(args, cwd=None, check=True, capture_output=False):
    """Run west for workspace update.

    Unlike build/config, `update` does not require the project venv: syncing
    the manifest repos only needs west + git.  So prefer the venv's west when
    it exists, but fall back to a system-wide `west` on PATH when there is no
    venv yet.  (build/config keep requiring the venv via utils.check_venv().)
    """
    if os.path.exists(utils.VENV_PYTHON_EXECUTABLE):
        return utils.run_west(args, cwd=cwd, check=check, capture_output=capture_output)
    west = shutil.which('west')
    if not west:
        print("Error: no .venv and no system 'west' found on PATH. Install west "
              "(e.g. pip install --user west), or run nuwa.py build/config once "
              "to bootstrap the venv.")
        sys.exit(2)
    # Plain environment (no PYTHONNOUSERSITE) so a user-site west imports fine.
    return subprocess.run([west] + list(args), cwd=cwd, check=check,
                          capture_output=capture_output, text=True)

def update_git_hooks():
    result = _run_west(['list', '--format', '{path}'], capture_output=True, check=False)
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
            _run_west(["forall", "-c", "git reset --hard && git clean -fd"])
        except subprocess.CalledProcessError as e:
            print("Error: Failed to clean workspace:", e)
            sys.exit(1)
        print("Clean workspace done")

    print("Update manifest...")
    try:
        subprocess.run(["git", "pull"], cwd="manifests", check=True, text=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print("Error: Failed to update manifest:", e)
        sys.exit(1)
    print("Update manifest done")

    print("Update workspace...")
    try:
        _run_west(["update", "-k", "-r"])
    except subprocess.CalledProcessError as e:
        print("Error: Failed to update workspace:", e)
        sys.exit(1)
    print("Update workspace done")

    print("Update Git hooks...")
    update_git_hooks()
    print("Update Git hooks done")

    print("Update done")

if __name__ == '__main__':
    main(len(sys.argv), sys.argv[1:])
