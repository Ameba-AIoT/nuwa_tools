#! /usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (c) 2024 Realtek Semiconductor Corp.
# SPDX-License-Identifier: Apache-2.0


import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import base.rtk_utils as utils

NUWA_SDK_QUERY_CFG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'query.json')
NUWA_SDK_DEFAULT_IMAGE_DIR = 'images'
NUWA_SDK_DEFAULT_BUILD_DIR = 'build'
NUWA_SDK_SOC_PROJECT_DIR = os.path.join('tools', 'meta_tools', 'scripts', 'soc_project')
NUWA_SDK_AXF2BIN_SCRIPT = os.path.join('tools', 'scripts', 'axf2bin.py')
NUWA_SDK_TOOLCHAIN_DEFAULT_PATH_WINDOWS = 'C:\\rtk-toolchain'
NUWA_SDK_TOOLCHAIN_DEFAULT_PATH_LINUX = '/opt/rtk-toolchain'

GCC_PREFIX = 'arm-none-eabi-'
GCC_SIZE = GCC_PREFIX + 'size'
GCC_OBJDUMP = GCC_PREFIX + 'objdump'
GCC_FROMELF = GCC_PREFIX + 'objcopy'
GCC_STRIP = GCC_PREFIX + 'strip'
GCC_NM = GCC_PREFIX + 'nm'

def main(argc, argv):
    parser = argparse.ArgumentParser(description=None)
    parser.add_argument('-a', '--app', help='application path')
    parser.add_argument('-b', '--build-dir', help='build directory')
    parser.add_argument('-d', '--device', help='device name')
    parser.add_argument('-i', '--image-dir', help='image directory')
    parser.add_argument('-t', '--toolchain-dir', help='toolchain directory')
    parser.add_argument('-p', '--pristine', action='store_true', help='pristine build')
    parser.add_argument('-c', '--clean', action='store_true', help='clean the build')

    args = parser.parse_args()

    if args.app == None:
        print('Warning: Invalid arguments, no application specified')
        parser.print_usage()
        sys.exit(1)
    else:
        pass

    if args.device == None:
        print('Warning: Invalid arguments, no device specified')
        parser.print_usage()
        sys.exit(1)
    else:
        pass

    if args.toolchain_dir == None:
        if os.name == 'nt':
            toolchain_dir = NUWA_SDK_TOOLCHAIN_DEFAULT_PATH_WINDOWS
        else:
            toolchain_dir = NUWA_SDK_TOOLCHAIN_DEFAULT_PATH_LINUX
        print('No toolchain specified, use default toolchain: ' + toolchain_dir)
    else:
        toolchain_dir = os.path.normcase(args.toolchain_dir)

    if os.path.exists(toolchain_dir):
        pass
    else:
        print("Error: Toolchain '" + toolchain_dir + "' does not exist")
        sys.exit(1)

    if args.build_dir == None:
        build_dir = NUWA_SDK_DEFAULT_BUILD_DIR
    else:
        build_dir = os.path.normcase(args.build_dir)

    if args.image_dir == None:
        image_dir = NUWA_SDK_DEFAULT_IMAGE_DIR
    else:
        image_dir = os.path.normcase(args.image_dir)

    utils.check_venv()

    cfg = None
    if os.path.exists(NUWA_SDK_QUERY_CFG_FILE):
        try:
            with open(NUWA_SDK_QUERY_CFG_FILE, 'r') as f:
                cfg = json.load(f)
        except:
            print('Error: Fail to load query configuration file "' + NUWA_SDK_QUERY_CFG_FILE + '"')
            sys.exit(2)
    else:
        print('Error: Query configuration file "' + NUWA_SDK_QUERY_CFG_FILE + '" does not exist')
        sys.exit(1)

    chip = None
    if args.device not in cfg['devices'].keys():
        print('Error: Unsupported device "' + args.device + '", valid values: ')
        [print(key) for key in cfg['devices'].keys()]
        sys.exit(1)
    else:
        chip = cfg['devices'][args.device]['chip']

    toolchain = cfg['chips'][chip]['toolchain']

    toolchain_path = None
    if os.name == 'nt':
        toolchain_path = os.path.join(toolchain_dir, toolchain, 'mingw32', 'newlib')
    else:
        toolchain_path = os.path.join(toolchain_dir, toolchain, 'linux', 'newlib')

    if os.path.exists(toolchain_path):
        pass
    else:
        print("Error: Toolchain '" + toolchain_path + "' does not exist")
        sys.exit(1)

    os.environ['ZEPHYR_TOOLCHAIN_VARIANT'] = 'gnuarmemb'
    os.environ['GNUARMEMB_TOOLCHAIN_PATH'] = toolchain_path

    if args.clean:
        try:
            subprocess.run([utils.VENV_PYTHON_EXECUTABLE, "-m" "west", "build", "-t", "clean", "-d", build_dir],
                        check=True,
                        text=True)
            print("Clean successful")
            sys.exit(0)
        except subprocess.CalledProcessError as e:
            print("Clean failed")
            print("Error:", e.stderr)
            sys.exit(1)

    build_cmd = [
        utils.VENV_PYTHON_EXECUTABLE, "-m", "west", "build", "-b", args.device, "-d", build_dir
    ]

    if args.pristine:
        build_cmd.extend(["-p", "always"])
    else:
        build_cmd.extend(["-p", "auto"])

    build_cmd.append(args.app)

    try:
        subprocess.run(build_cmd, check=True, text=True)
        print("Build successful")
    except subprocess.CalledProcessError as e:
        print("Build failed")
        print("Error:", e.stderr)
        sys.exit(1)

    if os.path.exists(image_dir):
        shutil.rmtree(image_dir)

    if args.device in cfg['devices'].keys():
        shutil.copytree(Path(build_dir) / 'images', Path(image_dir), dirs_exist_ok=True)
        print('Image location: ' + os.path.join(os.getcwd(), image_dir))
    else:
        print('Error: Unsupported device "' + args.device + '"')
        sys.exit(1)

if __name__ == '__main__':
    main(len(sys.argv), sys.argv[1:])
