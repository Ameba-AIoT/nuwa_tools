#! /usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (c) 2024 Realtek Semiconductor Corp.
# SPDX-License-Identifier: Apache-2.0

import os
import subprocess
import sys
import json

NUWA_SDK_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
NUWA_SDK_MANIFEST_DIR = os.path.join(NUWA_SDK_ROOT_DIR, 'manifests')
NUWA_META_TOOL_DIR = os.path.join('tools', 'meta_tools')
NUWA_CFG_FILE = os.path.join(NUWA_META_TOOL_DIR, 'nuwa.json')

NUWA_USAGE = '''\
Copyright(c) 2024, Realtek Semiconductor Corporation

Usage:
\tnuwa.py [-h] [-v] <command> [<options>]

Built-in options:
\t-h, --help\tprint usage information
\t-v, --version\tprint version information

Built-in commands:
\thelp:\t\tprint usage information for meta-tool or specific command

Extension commands:\
'''

def print_usage(cfg):
    print(cfg['brief'])
    print(NUWA_USAGE)
    for cmd in cfg['commands']:
        if len(cmd['name']) > 6:
            print('\t' + cmd['name'] + ':\t' + cmd['help'])
        else:
            print('\t' + cmd['name'] + ':\t\t' + cmd['help'])

def print_version(version):
    print('Realtek Nuwa SDK Meta Tool version: ' + version)

def _venv_python():
    directory = 'Scripts' if sys.platform == 'win32' else 'bin'
    executable = 'python.exe' if sys.platform == 'win32' else 'python'
    venv_py = os.path.join('.venv', directory, executable)
    return venv_py if os.path.exists(venv_py) else sys.executable

def run_west_flash(argv):
    """Run west flash directly, passing through all arguments."""
    # Show amebaflash help instead of west flash help
    if '-h' in argv or '--help' in argv or 'help' in argv:
        cmd = [_venv_python(), '-m', 'west', 'flash', '--runner', 'amebaflash', '--context']
        result = subprocess.run(cmd)
        sys.exit(result.returncode)

    cmd = [_venv_python(), '-m', 'west', 'flash', '--runner', 'amebaflash'] + argv
    result = subprocess.run(cmd)
    sys.exit(result.returncode)

def run_command(script, argv):
    script_path = os.path.join(NUWA_META_TOOL_DIR, script)
    translated = ['-h' if a == 'help' else a for a in argv]
    result = subprocess.run([_venv_python(), script_path] + translated)
    if result.returncode != 0:
        sys.exit(1)
    else:
        sys.exit(0)

def get_command_script(name, cfg):
    for cmd in cfg['commands']:
        if cmd['name'] == name:
            # Some commands (like flash) are handled directly by nuwa.py
            if 'script' not in cmd:
                return None
            return cmd['script']
    return None

def main(argc, argv):
    cfg = None
    help = False
    version = False
    command = None
    error = False
    script = None
    help_ext = False
    help_command = None

    if os.path.exists(NUWA_SDK_MANIFEST_DIR):
        pass
    else:
        print('Error: Wrong directory to run meta tool, it is only allowed to run under SDK root directory')
        sys.exit(2)

    if os.path.exists(NUWA_CFG_FILE):
        try:
            with open(NUWA_CFG_FILE, 'r') as f:
                cfg = json.load(f)
        except:
            print('Error: Fail to load meta tool configuration file "' + NUWA_CFG_FILE + '"')
            sys.exit(2)
    else:
        print('Error: Meta tool configuration file "' + NUWA_CFG_FILE + '" does not exist')
        sys.exit(1)

    if argc == 1:
        print('Warning: Invalid arguments')
        print_usage(cfg);
        sys.exit(1)
    else:
        pass

    idx = 0
    while idx < len(argv):
        arg = argv[idx]
        if arg.startswith('-h'):
            help = True
            idx += 1
        elif arg == '--help':
            help = True
            idx += 1
        elif arg.startswith('-v'):
            version = True
            idx += 1
        elif arg == '--version':
            version = True
            idx += 1
        elif arg.startswith('-'):
            error = True
            break
        elif arg == 'help':
            help_ext = True
            idx += 1
            if idx < len(argv):
                help_command = argv[idx]
                idx += 1
            break
        else:
            command = arg
            script = get_command_script(command, cfg)
            if script == None and command != 'flash':
                error = True
            break

    if help:
        print_usage(cfg)
        sys.exit(0)
    elif version:
        print_version(cfg['version'])
        sys.exit(0)
    elif help_ext:
        if help_command is None:
            print_usage(cfg)
            sys.exit(0)
        elif help_command == 'flash':
            run_west_flash(['-h'])
        else:
            help_script = get_command_script(help_command, cfg)
            if help_script is not None:
                run_command(help_script, ['-h'])
            else:
                error = True
    elif command == 'flash':
        run_west_flash(argv[1:])
    elif command != None and script != None:
        run_command(script, argv[1:])
    else:
        error = True

    if error:
        print('Warning: Invalid arguments')
        print_usage(cfg)
        sys.exit(1)
    else:
        pass

if __name__ == '__main__':
    main(len(sys.argv), sys.argv[1:])
