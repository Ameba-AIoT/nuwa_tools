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
NUWA_SDK_TOOLCHAIN_FILE = os.path.join('modules', 'hal', 'realtek', 'ameba', 'scripts', 'toolchain_db.json')
NUWA_SDK_DEFAULT_IMAGE_DIR = 'images'
NUWA_SDK_DEFAULT_BUILD_DIR = 'build'
NUWA_SDK_SOC_PROJECT_DIR = os.path.join('tools', 'meta_tools', 'scripts', 'soc_project')
NUWA_SDK_AXF2BIN_SCRIPT = os.path.join('tools', 'scripts', 'axf2bin.py')
NUWA_SDK_TOOLCHAIN_DEFAULT_PATH_WINDOWS = 'C:\\rtk-toolchain'
NUWA_SDK_TOOLCHAIN_DEFAULT_PATH_LINUX = os.path.expanduser('~/rtk-toolchain')

GCC_PREFIX = 'arm-none-eabi-'
GCC_SIZE = GCC_PREFIX + 'size'
GCC_OBJDUMP = GCC_PREFIX + 'objdump'
GCC_FROMELF = GCC_PREFIX + 'objcopy'
GCC_STRIP = GCC_PREFIX + 'strip'
GCC_NM = GCC_PREFIX + 'nm'

def run_cmd(cmd, cwd=None, quiet=False):
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True
        )
        if not quiet:
            print(f"[CMD] {' '.join(cmd) if isinstance(cmd, list) else cmd}")
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return -1, "", str(e)

def main(argc, argv):
    parser = argparse.ArgumentParser(description=None)

    # west-compatible parameters
    parser.add_argument('-b', '--board', help='board name (e.g., rtl8721f_evb)')
    parser.add_argument('-d', '--build-dir', help='build directory')
    parser.add_argument('-p', '--pristine', action='store_true', help='pristine build')
    parser.add_argument('--sysbuild', action='store_true', help='create multi domain build system')
    parser.add_argument('source_dir', nargs='?', help='application source directory')

    # nuwa-specific parameters
    parser.add_argument('-a', '--app', help='application path (alternative to positional source_dir)')
    parser.add_argument('-i', '--image-dir', help='image output directory')
    parser.add_argument('-c', '--clean', action='store_true', help='clean the build')

    # cmake options passthrough
    parser.add_argument('remainder', nargs=argparse.REMAINDER, help='cmake options passthrough to west')

    args = parser.parse_args()

    if args.build_dir == None:
        build_dir = NUWA_SDK_DEFAULT_BUILD_DIR
    else:
        build_dir = os.path.normcase(args.build_dir)

    utils.check_venv()

    if args.clean:
        try:
            utils.run_west(["build", "-t", "clean", "-d", build_dir])
            print("Clean successful")
            sys.exit(0)
        except subprocess.CalledProcessError:
            print("Clean failed")
            sys.exit(1)

    if args.board == None:
        print('Warning: Invalid arguments, no board specified')
        parser.print_usage()
        sys.exit(1)

    if args.source_dir == None:
        if args.app:
            source_dir = args.app
        else:
            print('Warning: Invalid arguments, no application specified')
            parser.print_usage()
            sys.exit(1)
    else:
        source_dir = args.source_dir

    if args.image_dir == None:
        image_dir = NUWA_SDK_DEFAULT_IMAGE_DIR
    else:
        image_dir = os.path.normcase(args.image_dir)

    if os.name == 'nt':
        toolchain_dir = Path(NUWA_SDK_TOOLCHAIN_DEFAULT_PATH_WINDOWS)
    else:
        toolchain_dir = Path(NUWA_SDK_TOOLCHAIN_DEFAULT_PATH_LINUX)

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
    # Support board variant
    board = args.board.split("/")[0]
    if board not in cfg['devices'].keys():
        print('Error: Unsupported board "' + args.board + '", valid values: ')
        [print(key) for key in cfg['devices'].keys()]
        sys.exit(1)
    else:
        chip = cfg['devices'][board]['chip']

    toolchain_db = None
    if os.path.exists(NUWA_SDK_TOOLCHAIN_FILE):
        try:
            with open(NUWA_SDK_TOOLCHAIN_FILE, 'r') as f:
                toolchain_db = json.load(f)
        except Exception:
            print('Error: Fail to load toolchain configuration file "' + NUWA_SDK_TOOLCHAIN_FILE + '"')
            sys.exit(2)
    else:
        print('Error: Toolchain configuration file "' + NUWA_SDK_TOOLCHAIN_FILE + '" does not exist')
        sys.exit(1)

    toolchain_id = None
    for k, v in toolchain_db.items():
        if isinstance(v, dict):
            devs = v.get('devices', [])
            if board in devs:
                toolchain_id = k
                break

    if toolchain_id is None:
        print('Error: Unsupported board "' + board + '" in toolchain file "' + NUWA_SDK_TOOLCHAIN_FILE + '"')
        sys.exit(1)

    toolchain_major, toolchain_minor = toolchain_id.rsplit('-', 1)
    toolchain = toolchain_major + '-' + toolchain_minor

    if os.name == 'nt':
        toolchain_path = toolchain_dir / toolchain / 'mingw32' / 'newlib'
    else:
        toolchain_path = toolchain_dir / toolchain / 'linux' / 'newlib'

    if toolchain_path.exists():
        pass
    else:
        print(f"Error: Toolchain '{toolchain_path}' does not exist")

        try:
            utils.run_west(["realtek", "ameba", "install", "-t", toolchain])
            print("toolchain install successful")
        except subprocess.CalledProcessError:
            print("toolchain install failed")
            sys.exit(1)

    # Always set toolchain env to ensure the correct versioned path is used,
    # regardless of any pre-existing values in the shell environment.
    os.environ['ZEPHYR_TOOLCHAIN_VARIANT'] = 'gnuarmemb'
    os.environ['GNUARMEMB_TOOLCHAIN_PATH'] = f"{toolchain_path}"

    west_args = ["build", "-b", args.board, "-d", build_dir]

    if args.pristine:
        west_args.extend(["-p", "always"])
    else:
        west_args.extend(["-p", "auto"])

    if args.sysbuild:
        west_args.extend(["--sysbuild"])

    west_args.append(source_dir)

    if args.remainder:
        west_args.extend(args.remainder)

    try:
        utils.run_west(west_args)
        print("Build successful")
    except subprocess.CalledProcessError:
        print("Build failed")
        sys.exit(1)

    if os.path.exists(image_dir):
        shutil.rmtree(image_dir)

    if board in cfg['devices'].keys():
        if args.sysbuild:
            shutil.copytree(Path(build_dir) / os.path.basename(source_dir) / 'images', Path(image_dir), dirs_exist_ok=True)
            shutil.copytree(Path(build_dir) / 'mcuboot' / 'images', Path(image_dir), dirs_exist_ok=True)
        else:
            shutil.copytree(Path(build_dir) / 'images', Path(image_dir), dirs_exist_ok=True)
        print('Image location: ' + os.path.join(os.getcwd(), image_dir))
    else:
        print('Error: Unsupported board "' + args.board + '"')
        sys.exit(1)

if __name__ == '__main__':
    main(len(sys.argv), sys.argv[1:])
