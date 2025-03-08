#! /usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (c) 2024 Realtek Semiconductor Corp.
# SPDX-License-Identifier: Apache-2.0


import argparse
import venv
import json
import os
import shutil
import subprocess
import sys


NUWA_SDK_VENV_DIR = '.venv'
NUWA_SDK_DEFAULT_BUILD_DIR = 'build'


def run_shell_cmd_with_output(cmd):
    return subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def check_venv():
    if os.path.exists(NUWA_SDK_VENV_DIR):
        pass
    else:
        # Create virtual environment if it does not exist
        try:
            venv.create(NUWA_SDK_VENV_DIR)
        except:
            print("Error: Fail to create Python virtual environment")
            sys.exit(2)


def main(argc, argv):
    parser = argparse.ArgumentParser(description=None)
    parser.add_argument('-b', '--build-dir', help='build directory')
    parser.add_argument('-d', '--device', help='device name')  # Reserved, for compatibility with RTOS SDK
    parser.add_argument('-g', '--gui', action='store_true', help='GUI config')

    args = parser.parse_args()

    if args.build_dir == None:
        build_dir = NUWA_SDK_DEFAULT_BUILD_DIR
    else:
        build_dir = os.path.normcase(args.build_dir)

    if os.path.exists(build_dir):
        pass
    else:
        print('Error: No build directory found, please do build first')
        sys.exit(1)

    check_venv()

    cmd_activate_venv = None
    cmd_deactivate_venv = None
    if os.name == 'nt':
        cmd_activate_venv = os.path.join(NUWA_SDK_VENV_DIR, 'Scripts', 'activate.bat')
        cmd_deactivate_venv = os.path.join(NUWA_SDK_VENV_DIR, 'Scripts', 'deactivate.bat')
    else:
        cmd_activate_venv = 'source ' + os.path.join(NUWA_SDK_VENV_DIR, 'bin', 'activate')
        cmd_deactivate_venv = 'deactivate'

    cmd = cmd_activate_venv + ' && '
    cmd += 'west build -t '
    if args.gui:
        cmd += 'guiconfig'
    else:
        cmd += 'menuconfig'
    cmd += ' -d "' + build_dir + '"'
    
    rc = os.system(cmd)
    if rc != 0:
        run_shell_cmd_with_output(cmd_deactivate_venv)
        print('Error: Fail to configure SDK')
        # Return code will be truncated, e.g.: 256 => 0, so the raw return code will not be used
        sys.exit(1)
    else:
        run_shell_cmd_with_output(cmd_deactivate_venv)


if __name__ == '__main__':
    main(len(sys.argv), sys.argv[1:])
