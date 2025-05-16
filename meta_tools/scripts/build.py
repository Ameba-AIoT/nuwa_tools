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


import base.rtk_utils as utils

NUWA_SDK_QUERY_CFG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'query.json')
NUWA_SDK_DEFAULT_IMAGE_DIR = 'images'
NUWA_SDK_DEFAULT_BUILD_DIR = 'build'
NUWA_SDK_IMAGE_SCRIPT_DIR = os.path.join('tools', 'image_scripts')
NUWA_SDK_AXF2BIN_SCRIPT = os.path.join(NUWA_SDK_IMAGE_SCRIPT_DIR, 'axf2bin.py')
NUWA_SDK_MANIFEST_JSON = os.path.join(NUWA_SDK_IMAGE_SCRIPT_DIR, 'manifest.json')
NUWA_SDK_TOOLCHAIN_DEFAULT_PATH_WINDOWS = 'C:\\msys64\\opt\\rtk-toolchain'
NUWA_SDK_TOOLCHAIN_DEFAULT_PATH_LINUX = '/opt/rtk-toolchain'

GCC_PREFIX = 'arm-none-eabi-'
GCC_SIZE = GCC_PREFIX + 'size'
GCC_OBJDUMP = GCC_PREFIX + 'objdump'
GCC_FROMELF = GCC_PREFIX + 'objcopy'
GCC_STRIP = GCC_PREFIX + 'strip'
GCC_NM = GCC_PREFIX + 'nm'


def run_shell_cmd_with_output(cmd):
    return subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


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

    target_dir = os.path.join(build_dir, 'zephyr')
    zephyr_bin = os.path.join(target_dir, 'zephyr.bin')
    zephyr_elf = os.path.join(target_dir, 'zephyr.elf')
    zephyr_map = os.path.join(target_dir, 'zephyr.map')
    zephyr_asm = os.path.join(target_dir, 'zephyr.asm')

    gcc_objdump = os.path.join(toolchain_path, 'bin', GCC_OBJDUMP)
    gcc_strip = os.path.join(toolchain_path, 'bin', GCC_STRIP)
    gcc_fromelf = os.path.join(toolchain_path, 'bin', GCC_FROMELF)

    cmd = gcc_objdump + ' -d "' + zephyr_elf + '" > ' + zephyr_asm
    subprocess.run(cmd, shell=True)

    if (args.device == 'rtl872xda_evb'):
        xip_image2_bin = os.path.join(target_dir, 'xip_image2.bin')
        target_pure_img2_axf = os.path.join(target_dir, 'target_pure_img2.axf')
        target_img2_map = os.path.join(target_dir, 'target_img2.map')
        km4_boot_all_bin = os.path.join(target_dir, 'km4_boot_all.bin')
        km0_image2_all_bin = os.path.join(target_dir, 'km0_image2_all.bin')
        km4_image2_all_bin = os.path.join(target_dir, 'km4_image2_all.bin')
        km4_image3_all_bin = os.path.join(target_dir, 'km4_image3_all.bin')
        km0_km4_app_tmp_bin = os.path.join(target_dir, 'km0_km4_app_tmp.bin')
        km0_image2_all_en_bin = os.path.join(target_dir, 'km0_image2_all_en.bin')
        km4_image2_all_en_bin = os.path.join(target_dir, 'km4_image2_all_en.bin')
        km4_image3_all_en_bin = os.path.join(target_dir, 'km4_image3_all_en.bin')
        km0_km4_app_ns_bin = os.path.join(target_dir, 'km0_km4_app_ns.bin')
        km0_km4_app_bin = os.path.join(target_dir, 'km0_km4_app.bin')
        manifest_bin = os.path.join(target_dir, 'manifest.bin')
        cert_bin = os.path.join(target_dir, 'cert.bin')
        entry_bin = os.path.join(target_dir, 'entry.bin')
        sram_2_bin = os.path.join(target_dir, 'sram_2.bin')
        psram_2_bin = os.path.join(target_dir, 'psram_2.bin')

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
        cmd = [utils.VENV_PYTHON_EXECUTABLE, NUWA_SDK_AXF2BIN_SCRIPT, 'pad', xip_image2_bin, '32']
        subprocess.run(cmd)

        cmd = 'echo "0e000020 T __flash_text_start__" > "' + target_img2_map + '" && '
        cmd += 'echo "0e000020 T __psram_image2_start__" >> "' + target_img2_map + '" && '
        cmd += 'echo "20010020 T __sram_image2_start__" >> "' + target_img2_map + '" && '
        cmd += 'echo "20004da0 D __image2_entry_func__" >> "' + target_img2_map + '"'
        subprocess.run(cmd, shell=True)

        cmd = [utils.VENV_PYTHON_EXECUTABLE, NUWA_SDK_AXF2BIN_SCRIPT, "prepend_header", entry_bin, "__image2_entry_func__", target_img2_map]
        subprocess.run(cmd)
        cmd = [utils.VENV_PYTHON_EXECUTABLE, NUWA_SDK_AXF2BIN_SCRIPT, "prepend_header", sram_2_bin, "__sram_image2_start__", target_img2_map]
        subprocess.run(cmd)
        cmd = [utils.VENV_PYTHON_EXECUTABLE, NUWA_SDK_AXF2BIN_SCRIPT, "prepend_header", psram_2_bin, "__psram_image2_start__", target_img2_map]
        subprocess.run(cmd)
        cmd = [utils.VENV_PYTHON_EXECUTABLE, NUWA_SDK_AXF2BIN_SCRIPT, "prepend_header", xip_image2_bin, "__flash_text_start__", target_img2_map]
        subprocess.run(cmd)

        cmd = 'cat "' + os.path.join(target_dir, 'xip_image2_prepend.bin') + '" "' + \
            os.path.join(target_dir, 'sram_2_prepend.bin') + '" "' + \
            os.path.join(target_dir, 'psram_2_prepend.bin') + '" "' + \
            os.path.join(target_dir, 'entry_prepend.bin') + '" > "' + \
            km4_image2_all_bin + '"'
        subprocess.run(cmd, shell=True)

        for root, dirs, files in os.walk(os.path.join('modules', 'hal', 'realtek', 'ameba', chip.lower(), 'bin')):
            for f in files:
                shutil.copy(os.path.join(root, f), target_dir)

        # TODO: replace by imagetool.py

        cmd = 'cat "' + km0_image2_all_bin + '" "' + km4_image2_all_bin + '" > "' + km0_km4_app_tmp_bin + '"'
        subprocess.run(cmd, shell=True)
        cmd = [utils.VENV_PYTHON_EXECUTABLE, NUWA_SDK_AXF2BIN_SCRIPT, 'cert', NUWA_SDK_MANIFEST_JSON, NUWA_SDK_MANIFEST_JSON, cert_bin, '0', 'app']
        subprocess.run(cmd)
        cmd = [utils.VENV_PYTHON_EXECUTABLE, NUWA_SDK_AXF2BIN_SCRIPT, "manifest", NUWA_SDK_MANIFEST_JSON, NUWA_SDK_MANIFEST_JSON, km0_km4_app_tmp_bin, manifest_bin, "app"]
        subprocess.run(cmd)

        if os.path.exists(manifest_bin):
            pass
        else:
            print('Error: Fail to generate manifest.bin')
            sys.exit(1)

        cmd = [utils.VENV_PYTHON_EXECUTABLE, NUWA_SDK_AXF2BIN_SCRIPT, 'rsip', km0_image2_all_bin, km0_image2_all_en_bin, '0x0c000000', NUWA_SDK_MANIFEST_JSON, 'app']
        subprocess.run(cmd)
        cmd = [utils.VENV_PYTHON_EXECUTABLE, NUWA_SDK_AXF2BIN_SCRIPT, 'rsip', km4_image2_all_bin, km4_image2_all_en_bin, '0x0e000000', NUWA_SDK_MANIFEST_JSON, 'app']
        subprocess.run(cmd)

        if os.path.exists(km4_image3_all_en_bin):
            cmd = 'cat "' + cert_bin + '" "' + manifest_bin + '" "' + km0_image2_all_bin + '" "' +  km4_image2_all_bin + '" "' + km4_image3_all_bin + '" > "' + km0_km4_app_ns_bin + '"'
            subprocess.run(cmd, shell=True)
            cmd = 'cat "' + cert_bin + '" "' + manifest_bin + '" "' + km0_image2_all_en_bin + '" "' +  km4_image2_all_en_bin + '" "' + km4_image3_all_en_bin + '" > "' + km0_km4_app_bin + '"'
            subprocess.run(cmd, shell=True)
        else:
            cmd = 'cat "' + cert_bin + '" "' + manifest_bin + '" "' + km0_image2_all_bin + '" "' +  km4_image2_all_bin + '" > "' + km0_km4_app_ns_bin + '"'
            subprocess.run(cmd, shell=True)
            cmd = 'cat "' + cert_bin + '" "' + manifest_bin + '" "' + km0_image2_all_en_bin + '" "' +  km4_image2_all_en_bin + '" > "' + km0_km4_app_bin + '"'
            subprocess.run(cmd, shell=True)

        os.remove(cert_bin)
        os.remove(manifest_bin)
        os.remove(km0_km4_app_tmp_bin)
        os.remove(km0_image2_all_en_bin)
        os.remove(km4_image2_all_en_bin)

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
        xip_image2_bin = os.path.join(target_dir, 'xip_image2.bin')
        sram_2_bin = os.path.join(target_dir, 'sram_2.bin')
        psram_2_bin = os.path.join(target_dir, 'psram_2.bin')
        target_pure_img2_axf = os.path.join(target_dir, 'target_pure_img2.axf')
        target_img2_map = os.path.join(target_dir, 'target_img2.map')
        bootloader_all_bin = os.path.join(target_dir, 'bootloader_all.bin')
        km0_image2_all_bin = os.path.join(target_dir, 'km0_image2_all.bin')
        km4_image2_all_bin = os.path.join(target_dir, 'km4_image2_all.bin')
        km0_km4_app_bin = os.path.join(target_dir, 'km0_km4_app.bin')

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

        cmd = [utils.VENV_PYTHON_EXECUTABLE, NUWA_SDK_AXF2BIN_SCRIPT, "pad", xip_image2_bin, "32"]
        subprocess.run(cmd)
        cmd = [utils.VENV_PYTHON_EXECUTABLE, NUWA_SDK_AXF2BIN_SCRIPT, "pad", sram_2_bin, "32"]
        subprocess.run(cmd)
        cmd = [utils.VENV_PYTHON_EXECUTABLE, NUWA_SDK_AXF2BIN_SCRIPT, "pad", psram_2_bin, "32"]
        subprocess.run(cmd)

        cmd = 'echo "0e000020 T __flash_text_start__" > "' + target_img2_map + '" && '
        cmd += 'echo "10003000 T __sram_image2_start__" >> "' + target_img2_map + '" && '
        cmd += 'echo "0e000020 T __psram_image2_start__" >> "' + target_img2_map + '"'
        subprocess.run(cmd, shell=True)

        cmd = [utils.VENV_PYTHON_EXECUTABLE, NUWA_SDK_AXF2BIN_SCRIPT, 'prepend_header', sram_2_bin, '__sram_image2_start__', target_img2_map]
        subprocess.run(cmd)
        cmd = [utils.VENV_PYTHON_EXECUTABLE, NUWA_SDK_AXF2BIN_SCRIPT, 'prepend_header', psram_2_bin, '__psram_image2_start__', target_img2_map]
        subprocess.run(cmd)
        cmd = [utils.VENV_PYTHON_EXECUTABLE, NUWA_SDK_AXF2BIN_SCRIPT, 'prepend_header', xip_image2_bin, '__flash_text_start__', target_img2_map]
        subprocess.run(cmd)

        cmd = 'cat "' + os.path.join(target_dir, 'xip_image2_prepend.bin') + '" "' + \
            os.path.join(target_dir, 'sram_2_prepend.bin') + '" "' + \
            os.path.join(target_dir, 'psram_2_prepend.bin') + '" > "' + \
            km4_image2_all_bin + '"'
        subprocess.run(cmd, shell=True)

        for root, dirs, files in os.walk(os.path.join('modules', 'hal', 'realtek', 'ameba', chip.lower(), 'bin')):
            for f in files:
                shutil.copy(os.path.join(root, f), target_dir)

        # TODO: replace by imagetool.py

        cmd = 'cat "' + km0_image2_all_bin + '" "' + km4_image2_all_bin + '" > "' + km0_km4_app_bin + '"'
        subprocess.run(cmd, shell=True)

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
