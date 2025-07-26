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


def run_shell_cmd_with_output(cmd):
    return subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

def axf2bin_pad(input_file, length):
    cmd = [utils.VENV_PYTHON_EXECUTABLE, NUWA_SDK_AXF2BIN_SCRIPT, 'pad', '-i', input_file, '-l', str(length)]
    subprocess.run(cmd)

def axf2bin_prepend_head(output_file, input_file, symbol, map_file):
    cmd = [utils.VENV_PYTHON_EXECUTABLE, NUWA_SDK_AXF2BIN_SCRIPT, "prepend_header",
           '-o', output_file,
           '-i', input_file,
           '-s', symbol,
           '-m', map_file]
    subprocess.run(cmd)

def ameba_axf2bin_fw_pack(target_dir, output_file, *input_files):
    cmd = [utils.VENV_PYTHON_EXECUTABLE, NUWA_SDK_AXF2BIN_SCRIPT, '--post-build-dir', target_dir,
           'fw_pack', '-o', output_file, *input_files]
    subprocess.run(cmd)

def concatenate_files(input_files, output_file):
    with open(output_file, 'wb') as outfile:
        for file in input_files:
            with open(file, 'rb') as infile:
                shutil.copyfileobj(infile, outfile)

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

    zephyr_bin = os.path.join(build_dir, 'zephyr', 'zephyr.bin')
    zephyr_elf = os.path.join(build_dir, 'zephyr', 'zephyr.elf')
    zephyr_map = os.path.join(build_dir, 'zephyr', 'zephyr.map')
    zephyr_asm = os.path.join(build_dir, 'zephyr', 'zephyr.asm')

    gcc_objdump = os.path.join(toolchain_path, 'bin', GCC_OBJDUMP)
    gcc_strip = os.path.join(toolchain_path, 'bin', GCC_STRIP)
    gcc_fromelf = os.path.join(toolchain_path, 'bin', GCC_FROMELF)

    cmd = gcc_objdump + ' -d "' + zephyr_elf + '" > ' + zephyr_asm
    subprocess.run(cmd, shell=True)

    if (args.device == 'rtl872xda_evb'):
        target_dir = Path(build_dir) / 'amebadplus_gcc_project'
        target_dir.mkdir(parents=True, exist_ok=True)

        xip_image2_bin = Path(target_dir) / 'xip_image2.bin'
        target_pure_img2_axf = Path(target_dir) / 'target_pure_img2.axf'
        target_img2_map = Path(target_dir) / 'target_img2.map'
        km4_boot_all_bin = Path(target_dir) / 'km4_boot_all.bin'
        km0_image2_all_bin = Path(target_dir) / 'km0_image2_all.bin'
        km4_image2_all_bin = Path(target_dir) / 'km4_image2_all.bin'
        km4_image3_all_bin = Path(target_dir) / 'km4_image3_all.bin'
        km0_km4_app_bin = Path(target_dir) / 'km0_km4_app.bin'
        entry_bin = Path(target_dir) / 'entry.bin'
        sram_2_bin = Path(target_dir) / 'sram_2.bin'
        psram_2_bin = Path(target_dir) / 'psram_2.bin'

        if os.path.exists(zephyr_bin) and os.path.exists(zephyr_elf):
            shutil.copyfile(zephyr_bin, xip_image2_bin)
            shutil.copyfile(zephyr_elf, target_pure_img2_axf)
        else:
            print('Error: No zephyr image generated')
            sys.exit(1)

        cmd =[gcc_strip, target_pure_img2_axf]
        subprocess.run(cmd)

        cmd = [gcc_fromelf, '-j', '.ram_image2.entry', '-Obinary', target_pure_img2_axf, entry_bin]
        subprocess.run(cmd)

        cmd = [gcc_fromelf, '-j', '.null.empty', '-Obinary', target_pure_img2_axf, sram_2_bin]
        subprocess.run(cmd)

        # let .ARM.extab/.ARM.exidx +- 1GB can jump to *(.text*)
        cmd = "grep __exidx_end '" + zephyr_map + "' | awk '{print $1}'"
        ret = run_shell_cmd_with_output(cmd)
        if ret.returncode == 0:
            arm_ex_addr = int(ret.stdout.strip(), 16)
        else:
            print(ret.stderr)
            sys.exit(1)

        if arm_ex_addr > 0x60000000:
            cmd = [gcc_fromelf, '-j', '.null.empty', '-Obinary', target_pure_img2_axf, psram_2_bin]
        else:
            cmd = [gcc_fromelf, '-j', '.null.empty', '-Obinary', target_pure_img2_axf, psram_2_bin]

        subprocess.run(cmd)

        print('========== Image manipulating start ==========')

        axf2bin_pad(xip_image2_bin, 32)

        map_contents = [
            "0e000020 T __flash_text_start__",
            "0e000020 T __psram_image2_start__",
            "20010020 T __sram_image2_start__",
            "20004da0 D __image2_entry_func__"
        ]
        target_img2_map.write_text('\n'.join(map_contents))

        entry_prepend_bin = Path(target_dir) / 'entry_prepend.bin'
        sram_2_prepend_bin = Path(target_dir) / 'sram_2_prepend.bin'
        psram_2_prepend_bin = Path(target_dir) / 'psram_2_prepend.bin'
        xip_image2_prepend_bin = Path(target_dir) / 'xip_image2_prepend.bin'

        axf2bin_prepend_head(entry_prepend_bin, entry_bin, '__image2_entry_func__', target_img2_map)
        axf2bin_prepend_head(sram_2_prepend_bin, sram_2_bin, '__sram_image2_start__', target_img2_map)
        axf2bin_prepend_head(psram_2_prepend_bin, psram_2_bin, '__psram_image2_start__', target_img2_map)
        axf2bin_prepend_head(xip_image2_prepend_bin, xip_image2_bin, '__flash_text_start__', target_img2_map)

        input_files = [xip_image2_prepend_bin, sram_2_prepend_bin, psram_2_prepend_bin, entry_prepend_bin]
        concatenate_files(input_files, km4_image2_all_bin)

        source_dir = Path('modules') / 'hal' / 'realtek' / 'ameba' / chip.lower() / 'bin'
        for file_path in source_dir.rglob('*'):
            if file_path.is_file():
                shutil.copy(file_path, target_dir)

        shutil.copy(os.path.join(NUWA_SDK_SOC_PROJECT_DIR, 'amebadplus', 'manifest.json5'), target_dir)
        shutil.copy(os.path.join(NUWA_SDK_SOC_PROJECT_DIR, 'amebadplus', 'ameba_layout.ld'), target_dir)

        cmd = [utils.VENV_PYTHON_EXECUTABLE, NUWA_SDK_AXF2BIN_SCRIPT, 'cut', '-o', target_dir / 'km4_boot.bin', '-i', km4_boot_all_bin, '-l', '4096']
        subprocess.run(cmd)
        ameba_axf2bin_fw_pack(target_dir.resolve(), km4_boot_all_bin, '--image1', target_dir / 'km4_boot.bin')

        if os.path.exists(km4_image3_all_bin):
            ameba_axf2bin_fw_pack(target_dir.resolve(), km0_km4_app_bin, '--image2', km0_image2_all_bin, km4_image2_all_bin, '--image3', km4_image3_all_bin)
        else:
            ameba_axf2bin_fw_pack(target_dir.resolve(), km0_km4_app_bin, '--image2', km0_image2_all_bin, km4_image2_all_bin)

        print('=========== Image manipulating end ===========')

        if os.path.exists(km0_km4_app_bin):
            os.makedirs(image_dir)
            shutil.move(km4_boot_all_bin, image_dir)
            shutil.move(km0_km4_app_bin, image_dir)
            print('Image location: ' + os.path.join(os.getcwd(), image_dir))
            print('Build done')
        else:
            print('Error: Fail to manipulate images')
            sys.exit(1)
    elif (args.device == 'rtl872xd_evb'):
        target_dir = Path(build_dir) / 'amebad_gcc_project'
        target_dir.mkdir(parents=True, exist_ok=True)

        xip_image2_bin = Path(target_dir) / 'xip_image2.bin'
        sram_2_bin = Path(target_dir) / 'sram_2.bin'
        psram_2_bin = Path(target_dir) / 'psram_2.bin'
        target_pure_img2_axf = Path(target_dir) / 'target_pure_img2.axf'
        target_img2_map = Path(target_dir) / 'target_img2.map'
        bootloader_all_bin = Path(target_dir) / 'bootloader_all.bin'
        km0_image2_all_bin = Path(target_dir) / 'km0_image2_all.bin'
        km4_image2_all_bin = Path(target_dir) / 'km4_image2_all.bin'
        km4_image3_all_bin = Path(target_dir) / 'km4_image3_all.bin'
        km0_km4_app_bin = Path(target_dir) / 'km0_km4_app.bin'

        if os.path.exists(zephyr_bin) and os.path.exists(zephyr_elf):
            shutil.copyfile(zephyr_bin, xip_image2_bin)
            shutil.copyfile(zephyr_elf, target_pure_img2_axf)
        else:
            print('Error: No zephyr image generated')
            sys.exit(1)

        cmd = [gcc_strip, target_pure_img2_axf]
        subprocess.run(cmd)

        cmd = [gcc_fromelf, '-j', '.ram_image2.entry', '-Obinary', target_pure_img2_axf, sram_2_bin]
        subprocess.run(cmd)

        cmd = [gcc_fromelf, '-j', '.null.empty', '-Obinary', target_pure_img2_axf, psram_2_bin]
        subprocess.run(cmd)

        print('========== Image manipulating start ==========')

        axf2bin_pad(xip_image2_bin, 32)
        axf2bin_pad(sram_2_bin, 32)
        axf2bin_pad(psram_2_bin, 32)

        map_contents = [
            "0e000020 T __flash_text_start__",
            "0e000020 T __psram_image2_start__",
            "10003000 T __sram_image2_start__",
        ]
        target_img2_map.write_text('\n'.join(map_contents))

        sram_2_prepend_bin = Path(target_dir) / 'sram_2_prepend.bin'
        psram_2_prepend_bin = Path(target_dir) / 'psram_2_prepend.bin'
        xip_image2_prepend_bin = Path(target_dir) / 'xip_image2_prepend.bin'

        axf2bin_prepend_head(sram_2_prepend_bin, sram_2_bin, '__sram_image2_start__', target_img2_map)
        axf2bin_prepend_head(psram_2_prepend_bin, psram_2_bin, '__psram_image2_start__', target_img2_map)
        axf2bin_prepend_head(xip_image2_prepend_bin, xip_image2_bin, '__flash_text_start__', target_img2_map)

        input_files = [xip_image2_prepend_bin, sram_2_prepend_bin, psram_2_prepend_bin]
        concatenate_files(input_files, km4_image2_all_bin)

        source_dir = Path('modules') / 'hal' / 'realtek' / 'ameba' / chip.lower() / 'bin'
        for file_path in source_dir.rglob('*'):
            if file_path.is_file():
                shutil.copy(file_path, target_dir)

        shutil.copy(os.path.join(NUWA_SDK_SOC_PROJECT_DIR, 'amebad', 'manifest.json5'), target_dir)
        shutil.copy(os.path.join(NUWA_SDK_SOC_PROJECT_DIR, 'amebad', 'ameba_layout.ld'), target_dir)

        if os.path.exists(km4_image3_all_bin):
            ameba_axf2bin_fw_pack(target_dir.resolve(), km0_km4_app_bin, '--image2', km0_image2_all_bin, km4_image2_all_bin, '--image3', km4_image3_all_bin, '--sboot-for-image', '1')
        else:
            ameba_axf2bin_fw_pack(target_dir.resolve(), km0_km4_app_bin, '--image2', km0_image2_all_bin, km4_image2_all_bin, '--sboot-for-image', '1')

        print('=========== Image manipulating end ===========')

        if os.path.exists(km0_km4_app_bin):
            os.makedirs(image_dir)
            shutil.move(bootloader_all_bin, image_dir)
            shutil.move(km0_km4_app_bin, image_dir)
            print('Image location: ' + os.path.join(os.getcwd(), image_dir))
            print('Build done')
        else:
            print('Error: Fail to manipulate images')
            sys.exit(1)
    else:
        print('Error: Unsupported device "' + args.device + '"')
        sys.exit(1)


if __name__ == '__main__':
    main(len(sys.argv), sys.argv[1:])
