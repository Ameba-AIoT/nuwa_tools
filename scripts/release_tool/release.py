#! /usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (c) 2024 Realtek Semiconductor Corp.
# SPDX-License-Identifier: Apache-2.0

import os
import sys
import subprocess
import argparse
import shutil
import re
import json
import glob
from typing import List
import random

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SDK_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '../../..'))

sys.path.append(os.path.dirname(SCRIPT_DIR))
from ameba_soc_utils import SocManager

os.environ['PARALLEL_BUILD'] = 'true'

def delete_lines_containing(filepath, patterns):
    if not os.path.isfile(filepath):
        return

    with open(filepath, 'r', encoding='utf-8') as file:
        lines = file.readlines()

    with open(filepath, 'w', encoding='utf-8') as file:
        for line in lines:
            if not any(pattern in line for pattern in patterns):
                file.write(line)

def delete_compil_lib(rootdir):
    delete_lines_containing(
        os.path.join(rootdir, 'component/soc/amebasmart/atf/plat/realtek/sheipa/sp_min/sp_min-sheipa.mk'),
         ['MAKE_LIB', 'lib/libpm.a']
    )

def single_build(soc_name, filename=None):
    if filename is not None:
        conf = ' -f '
        if isinstance(filename, list):
            for f in filename:
                conf += f + ' '
        else:
            conf += filename
    else:
        conf = ''
    cmd = 'cd ' + SDK_ROOT + f' && python ameba.py menuconfig {soc_name}' + conf
    # print(cmd)
    result = subprocess.run(cmd, shell = True, check = True)
    if result.returncode != 0:
        print(f'Error: menuconfig failed for {filename}')
        sys.exit(result.returncode)
    cmd = 'cd ' + SDK_ROOT + f' && python ameba.py build {soc_name} -D BUILD_FOR_RLS=1'
    result = subprocess.run(cmd, shell = True, check = True)
    if result.returncode != 0:
        print(f'Error: build failed for {filename}')
        sys.exit(result.returncode)
    shutil.rmtree(os.path.join(SDK_ROOT, f'build_{soc_name}/build'))


def build_lib(chip: str, soc_name: str):
    project_dir = os.path.join(SDK_ROOT, f'component/soc/{chip}/project')
    if not os.path.isdir(project_dir): # for temporary compatibility
        project_dir = os.path.join(SDK_ROOT, f'{chip}_gcc_project')
    project_paths = glob.glob(os.path.join(project_dir, 'project_*'))
    for dir in project_paths:
        for sdk in ['', 'asdk', 'vsdk']:
            if os.path.exists(os.path.join(dir, sdk)):
                shutil.rmtree(os.path.join(dir, f'{sdk}/lib/application'), ignore_errors=True)
                shutil.rmtree(os.path.join(dir, f'{sdk}/lib/soc'), ignore_errors=True)

    subprocess.run('cd ' + SDK_ROOT + f' && python ameba.py menuconfig {soc_name} -c', shell = True, check = True)

    # Define conf lists for each chip
    conf_lists = {
        'amebadplus': [
            ['rls_sdio_wpaoh.conf'],
            ['rls_spi_wpaoh.conf'],
            ['rls_usb_wpaoh.conf'],
            ['rls_sdio_wpaoh_tcpip.conf'],
            ['rls_spi_wpaoh_tcpip.conf'],
            ['rls_usb_wpaoh_tcpip.conf'],
            ['rls_sdio_wpaod.conf'],
            ['rls_spi_wpaod.conf'],
            ['rls_usb_wpaod.conf'],
            ['rls_sdio_wpaod_tcpip.conf'],
            ['rls_spi_wpaod_tcpip.conf'],
            ['rls_usb_wpaod_tcpip.conf'],
            ['rls_normal_mp.conf'],
            ['rls_shrink_mp.conf'],
            ['rls_audio.conf'],
            ['rls_gui_lib.conf'],
            [f'{project_dir}/default.conf'],
        ],
        'amebagreen2': [
            ['rls_audio.conf'],
            ['rls_sdio_wpaoh.conf'],
            ['rls_spi_wpaoh.conf'],
            ['rls_usb_wpaoh.conf'],
            ['rls_sdio_wpaoh_tcpip.conf'],
            ['rls_spi_wpaoh_tcpip.conf'],
            ['rls_usb_wpaoh_tcpip.conf'],
            ['rls_sdio_wpaod.conf'],
            ['rls_spi_wpaod.conf'],
            ['rls_usb_wpaod.conf'],
            ['rls_sdio_wpaod_tcpip.conf'],
            ['rls_spi_wpaod_tcpip.conf'],
            ['rls_usb_wpaod_tcpip.conf'],
            ['rls_normal_mp.conf'],
            ['rls_shrink_mp.conf'],
            [f'{project_dir}/default.conf'],
        ],
        'amebalite': [
            ['rls_audio_km4_ap.conf'],
            ['rls_normal_mp_km4_ap.conf'],
            ['rls_shrink_mp_km4_ap.conf'],
            ['rls_audio_kr4_ap.conf'],
            ['rls_normal_mp_kr4_ap.conf'],
            ['rls_gui_km4_lib.conf'],
            ['rls_gui_kr4_lib.conf'],
            ['rls_spi_wpaoh.conf'],
            ['rls_spi_wpaoh_tcpip.conf'],
            ['rls_spi_wpaod.conf'],
            ['rls_spi_wpaod_tcpip.conf'],
            [f'{project_dir}/default.conf'],
        ],
        'amebasmart': [
            [f'{project_dir}/default.conf'],
            ['rls_mp_shrink.conf'],
            ['rls_mp_expand.conf'],
            ['rls_ca32_single_core.conf'],
            ['rls_mp_shrink.conf', 'rls_km4_audio.conf'],
            ['rls_bt.conf', 'rls_ca32_audio.conf', 'rls_ca32_gui_lib.conf'],
            ['rls_bt.conf', 'rls_mp_shrink.conf'],
            ['rls_km4_ap.conf', 'rls_km4_third_lib.conf', 'rls_bt.conf', 'rls_km4_audio.conf', 'rls_xip_flash.conf', 'rls_km4_gui_lib.conf'],
            ['rls_km4_ap.conf', 'rls_mp_shrink.conf'],
            ['rls_km4_ap.conf', 'rls_mp_expand.conf'],
        ],
    }
    confs = conf_lists.get(chip, [])
    conf_dir = os.path.join(SCRIPT_DIR, chip, 'confs_release_tool')
    for conf_list in confs:
        conf_files = [os.path.join(conf_dir, f) for f in conf_list]
        single_build(soc_name, conf_files)


def delete_lib_gitignore(filename):
    with open(filename, 'r') as r:
        lines = r.readlines()

    lines_to_remove = [
        'asdk/lib',
        'vsdk/lib',
        '/component/soc/**/project/**/lib/'
    ]
    with open(filename, 'w') as w:
        write_flag = 1
        for line in lines:
            if line.strip().startswith('# ignore submodules start'):
                write_flag = 0
            elif line.strip().startswith('# ignore submodules end'):
                write_flag = 1

            is_target_line = any(target in line for target in lines_to_remove)
            if not is_target_line and write_flag == 1:
                w.write(line)


def main(argc, argv):
    parser = argparse.ArgumentParser(description=None)
    parser.add_argument(
        '-c',
        '--chip',
        choices=['amebadplus', 'amebagreen2', 'amebalite', 'amebasmart'],
        required=True,
        help='chip name')
    parser.add_argument(
        "-v",
        "--version",
        help="sdk version, e.g. release.py [-v 11.0a-alpha]"
    )
    parser.add_argument(
        "--submodules",
        action='store_true',
        help="sdk release for submodules, e.g. release.py [--submodules]"
    )
    args = parser.parse_args()

    chip = args.chip

    output_dir_map = {
        "amebadplus": "sdk-AmebaDplus",
        "amebagreen2": "sdk-AmebaGreen2",
        "amebalite": "sdk-AmebaLite",
        "amebasmart": "sdk-RTL8730E",
    }
    version_map = {
        "amebadplus": "11.0a-alpha",
        "amebagreen2": "11.0a-alpha",
        "amebalite": "10.0f-beta",
        "amebasmart": "8.1c-alfa",
    }

    if not args.version:
        args.version = version_map.get(chip)

    folder = output_dir_map.get(chip, f"sdk-{chip}") #'sdk-' + chip.capitalize()
    TARGET_FOLDER = folder + '_v' + args.version
    print('version to release: ' + TARGET_FOLDER)

    manager = SocManager()
    soc_map = manager.soc_map
    keys = [k for k, v in soc_map.items() if v == chip]
    if len(keys) > 1:
        soc_name = random.choice(keys)
    else:
        soc_name = keys[0] if keys else None

    # build lib
    build_lib(chip, soc_name)

    # copy files
    autorelease_script = os.path.join(SCRIPT_DIR, 'auto_release_sdk_files_process.py')
    subprocess.run([sys.executable, autorelease_script, '--chip', chip, '--out-dir', folder], check=True)

    if os.path.exists(TARGET_FOLDER):
        shutil.rmtree(TARGET_FOLDER)

    shutil.move(folder, TARGET_FOLDER)

    # add rls flag in CMakeLists
    KconfigPath = f'{TARGET_FOLDER}/component/soc/{chip}/project/Kconfig'
    if not os.path.exists(KconfigPath): # for temporary compatibility
        KconfigPath = f'{TARGET_FOLDER}/{chip}_gcc_project/Kconfig'

    with open(KconfigPath, 'r') as f:
        content = f.read()
        new_content = re.sub( r'config AMEBA_RLS\s+def_bool n', 'config AMEBA_RLS\n  def_bool y', content, flags=re.M)
    with open(KconfigPath, 'w') as f:
        f.write(new_content)


    delete_lib_gitignore(os.path.join(TARGET_FOLDER, '.gitignore'))

    if chip == 'amebasmart':
        delete_compil_lib(TARGET_FOLDER)

    # check release sdk
    temp_sdk_name = f'temp_sdk_{chip}'
    if os.path.exists(temp_sdk_name):
        shutil.rmtree(temp_sdk_name)
    shutil.copytree(TARGET_FOLDER, temp_sdk_name)
    result = subprocess.run('cd ' + temp_sdk_name + f' && python ameba.py build {soc_name}', shell = True, check = True)
    if result.returncode != 0:
        print(f"Error: '{temp_sdk_name}' build failed for release sdk check")
        sys.exit(result.returncode)
    subprocess.run('cd ' + temp_sdk_name + f' && python ameba.py menuconfig {soc_name} -c', shell = True, check = True)
    shutil.rmtree(temp_sdk_name)

    def move_and_delete_dirs(submodule, source_dir, target_dirs: List):
        print(source_dir, target_dirs)
        dest_dir = source_dir + '_' + submodule
        if os.path.exists(dest_dir):
            shutil.rmtree(dest_dir)
        for target_dir in target_dirs:
            _source_dir = os.path.join(source_dir, target_dir)
            print(f'{_source_dir}------------>{dest_dir}')
            if os.path.exists(_source_dir):
                shutil.move(_source_dir, dest_dir)
            else:
                print(f'{_source_dir} not exists!')
        if os.path.exists(dest_dir):
            subprocess.run('tar -zcvf ' +  dest_dir + '.tgz ' + dest_dir, shell = True, check = True)
            shutil.rmtree(dest_dir)

    # # tar
    if args.submodules:
        submd_file = os.path.join(SCRIPT_DIR, 'release_submodules.json')
        if os.path.exists(submd_file):
            with open(submd_file, 'r', encoding='utf-8') as f:
                submodules = json.load(f)
            for submodule, paths in submodules.items():
                move_and_delete_dirs(submodule, TARGET_FOLDER, paths)

    # tar
    subprocess.run('tar -zcvf ' + TARGET_FOLDER + '.tgz ' + TARGET_FOLDER, shell = True, check = True)

    shutil.rmtree(TARGET_FOLDER)

if __name__ == '__main__':
    main(len(sys.argv), sys.argv[1:])
