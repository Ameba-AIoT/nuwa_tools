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
NUWA_SDK_TOOLCHAIN_DEFAULT_PATH_LINUX = '/opt/rtk-toolchain'

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
    parser.add_argument('-a', '--app', help='application path')
    parser.add_argument('-b', '--build-dir', help='build directory')
    parser.add_argument('-d', '--device', help='device name')
    parser.add_argument('-i', '--image-dir', help='image directory')
    parser.add_argument('-t', '--toolchain-dir', help='toolchain directory')
    parser.add_argument('-p', '--pristine', action='store_true', help='pristine build')
    parser.add_argument('-c', '--clean', action='store_true', help='clean the build')
    parser.add_argument('--sysbuild', action='store_true', help='create multi domain build system')
    parser.add_argument('remainder', nargs=argparse.REMAINDER, help='cmake options passthrough to west')

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
            toolchain_dir = Path(NUWA_SDK_TOOLCHAIN_DEFAULT_PATH_WINDOWS)
        else:
            toolchain_dir = Path(NUWA_SDK_TOOLCHAIN_DEFAULT_PATH_LINUX)
        print(f"No toolchain specified, use default toolchain: {toolchain_dir}")
    else:
        toolchain_dir = Path(os.path.normcase(args.toolchain_dir)).resolve()

    if os.path.exists(toolchain_dir):
        pass
    else:
        print(f"Error: Toolchain '{toolchain_dir}' does not exist")
        try:
            toolchain_dir.mkdir(parents=True, exist_ok=True)
            print(f"Create Toolchain Dir {toolchain_dir} Success")
        except PermissionError:
            sys.exit(f"Create Toolchain Dir Failed. May Not Have Permission!")

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
    # Support board variant, refer to:
    # https://docs.zephyrproject.org/latest/hardware/porting/board_porting.html#board-terminology
    device = args.device.split("/")[0]
    if device not in cfg['devices'].keys():
        print('Error: Unsupported device "' + args.device + '", valid values: ')
        [print(key) for key in cfg['devices'].keys()]
        sys.exit(1)
    else:
        chip = cfg['devices'][device]['chip']

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
            if device in devs:
                toolchain_id = k
                break

    if toolchain_id is None:
        print('Error: Unsupported device "' + device + '" in toolchain file "' + NUWA_SDK_TOOLCHAIN_FILE + '"')
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

        install_cmd = [
            utils.VENV_PYTHON_EXECUTABLE, "-m", "west", "realtek", "ameba", "install", "-t", toolchain
        ]
        
        try:
            subprocess.run(install_cmd, check=True, text=True)
            print("toolchain install successful")
        except subprocess.CalledProcessError as e:
            print("toolchain install failed")
            print("Error:", e.stderr)
            sys.exit(1)

    os.environ['ZEPHYR_TOOLCHAIN_VARIANT'] = 'gnuarmemb'
    os.environ['GNUARMEMB_TOOLCHAIN_PATH'] = f"{toolchain_path}"

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

    if args.sysbuild:
        build_cmd.extend(["--sysbuild"])

    build_cmd.append(args.app)

    if args.remainder:
        build_cmd.extend(args.remainder)

    try:
        subprocess.run(build_cmd, check=True, text=True)
        print("Build successful")
    except subprocess.CalledProcessError as e:
        print("Build failed")
        print("Error:", e.stderr)
        sys.exit(1)

    if os.path.exists(image_dir):
        shutil.rmtree(image_dir)

    if device in cfg['devices'].keys():
        if args.sysbuild:
            shutil.copytree(Path(build_dir) / os.path.basename(args.app) / 'images', Path(image_dir), dirs_exist_ok=True)
            shutil.copytree(Path(build_dir) / 'mcuboot' / 'images', Path(image_dir), dirs_exist_ok=True)
        else:
            shutil.copytree(Path(build_dir) / 'images', Path(image_dir), dirs_exist_ok=True)
        print('Image location: ' + os.path.join(os.getcwd(), image_dir))
    else:
        print('Error: Unsupported device "' + args.device + '"')
        sys.exit(1)

if __name__ == '__main__':
    main(len(sys.argv), sys.argv[1:])
