#! /usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (c) 2024 Realtek Semiconductor Corp.
# SPDX-License-Identifier: Apache-2.0


import argparse
import os
import subprocess
import sys

import base.rtk_utils as utils

NUWA_SDK_DEFAULT_BUILD_DIR = 'build'


def run_shell_cmd_with_output(cmd):
    return subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def main(argc, argv):
    parser = argparse.ArgumentParser(description=None)
    parser.add_argument('-b', '--build-dir', help='build directory')
    parser.add_argument('-d', '--device', help='device name')  # Reserved, for compatibility with RTOS SDK
    parser.add_argument('-g', '--gui', action='store_true', help='GUI config')
    parser.add_argument('-c', '--clean', action='store_true', help='clean menuconfig')

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

    utils.check_venv()
    if args.clean:
        try:
            subprocess.run([utils.VENV_PYTHON_EXECUTABLE, "-m" "west", "build", "-t", "pristine", "-d", build_dir], 
                        check=True, 
                        text=True)
            print("Clean successful")
            sys.exit(0)
        except subprocess.CalledProcessError as e:
            print("Clean failed")
            print("Error:", e.stderr)
            sys.exit(1)

    west_build_cmd = [utils.VENV_PYTHON_EXECUTABLE, "-m", "west", "build", "-d", build_dir]
    if args.gui:
        west_build_cmd.extend(["-t", "guiconfig"])
    else:
        west_build_cmd.extend(["-t", "menuconfig"])

    try:
        subprocess.run(west_build_cmd, check=True, text=True)
        print("Configuration successful")
    except subprocess.CalledProcessError as e:
        print("Configuration failed")
        print("Error:", e.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main(len(sys.argv), sys.argv[1:])
