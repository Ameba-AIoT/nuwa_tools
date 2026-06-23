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


def main(argc, argv):
    parser = argparse.ArgumentParser(description=None)
    parser.add_argument('-d', '--build-dir', help='build directory')
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
            utils.run_west(["build", "-t", "pristine", "-d", build_dir])
            print("Clean successful")
            sys.exit(0)
        except subprocess.CalledProcessError:
            print("Clean failed")
            sys.exit(1)

    west_args = ["build", "-d", build_dir]
    if args.gui:
        west_args.extend(["-t", "guiconfig"])
    else:
        west_args.extend(["-t", "menuconfig"])

    try:
        utils.run_west(west_args)
        print("Configuration successful")
    except subprocess.CalledProcessError:
        print("Configuration failed")
        sys.exit(1)


if __name__ == '__main__':
    main(len(sys.argv), sys.argv[1:])
