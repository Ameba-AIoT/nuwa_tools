#! /usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (c) 2024 Realtek Semiconductor Corp.
# SPDX-License-Identifier: Apache-2.0

import argparse
import json
import os
import subprocess
import sys
import uuid

NUWA_SDK_BRIEF_DESC = 'Realtek Nuwa Zephyr SDK'
NUWA_SDK_MANIFEST_DIR = 'manifests'
NUWA_SDK_QUERY_CFG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'query.json')
NUWA_SDK_APP_FILE = 'main.c'

CMD_QUERY_BOARD = 'west boards -n "rtl.*"'
CMD_GET_MANIFEST_PATH = 'west manifest --path'
CMD_GET_MANIFEST_URL = "cat " + os.path.join(NUWA_SDK_MANIFEST_DIR, '.git', 'config') + " | grep url | cut -d\"=\" -f 2"


def run_shell_cmd_with_output(cmd):
    return subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def do_query_app(sdkroot, cfg):
    include_path_list = [os.path.normpath(os.path.join(sdkroot, x)) for x in cfg.get("apps", {}).get("include", [])]
    exclude_path_list = [os.path.normpath(os.path.join(sdkroot, x)) for x in cfg.get("apps", {}).get("exclude", [])]

    class Node():
        def __init__(self, path, sdkroot):
            self.path = path
            self.sdkroot = sdkroot
            self.name = os.path.basename(path)
            self.parent_path = os.path.dirname(path)
            self.parent = None
            self.children = []

        @property
        def json_prepare(self):
            if self.children:
                children_list = []
                for child in self.children:
                    children_list.append(child.json_prepare)
                return {self.name: children_list}
            else:
                return {self.name: os.path.relpath(self.path, os.path.basename(self.sdkroot))}

        def __repr__(self):
            return f"Node({self.name} {self.parent_path})"

    nodes_dict = {}
    for include_path in include_path_list:
        # use os.walk can run faster than path rglob
        if os.path.exists(include_path):
            for root, dirs, files in os.walk(include_path):
                for file in files:
                    if file == "main.c":
                        app = os.path.dirname(root)
                        for exclude_path in exclude_path_list:
                            if app.startswith(exclude_path):
                                break
                        else:
                            rel_path = os.path.relpath(app, os.path.dirname(sdkroot))
                            node = Node(rel_path, sdkroot)
                            nodes_dict.update({rel_path: node})

    # restructure
    node_paths = list(nodes_dict.keys())
    for node_path in node_paths:
        node = nodes_dict[node_path]
        while node.parent_path:
            parent = nodes_dict.get(node.parent_path)
            if parent is None:
                parent = Node(node.parent_path, sdkroot)
                nodes_dict.update({parent.path: parent})
            if node not in parent.children:
                parent.children.append(node)
            node.parent = node
            node = parent

    root_node = nodes_dict.get(os.path.basename(sdkroot))
    if root_node:
        ret_dict = root_node.json_prepare
        ret_dict = {"apps": ret_dict[os.path.basename(sdkroot)]}
        ret = json.dumps(ret_dict, indent=4)
    else:
        raise Exception('Can not get any apps!')
    print(ret)


def do_query_device(cfg):
    # Query against key words
    # os.system(CMD_QUERY_BOARD)
    # Query against configuration file
    devices = dict()
    for key, value in cfg['devices'].items():
        chip = value['chip']
        chip_cfg = cfg['chips'][value['chip']]
        value['core'] = chip_cfg['core']
        value['target'] = os.path.join('zephyr','zephyr.elf')
        value['toolchain'] = chip_cfg['toolchain']
        value['jlinkScript'] = os.path.join('tools', 'meta_tools', 'scripts', 'jlink_scripts', os.path.normcase(chip_cfg['jlinkScript']))
        value['path'] = os.path.normcase(value['path'])
        devices[key] = value
    ret = json.dumps(devices, indent=4)
    print(ret)


def do_query_info(sdkroot, cfg):
    repo_info = cfg['info']
    info = dict()
    info['uuid'] = str(uuid.uuid4())
    info['brief'] = repo_info['brief']
    info['details'] = None
    info['soc'] = repo_info['soc']
    info['os'] = repo_info['os']
    info['server'] = None
    info['vcs'] = repo_info['vcs']
    info['metaTool'] = repo_info['meta']
    info['metaToolPath'] = os.path.join('tools', 'meta_tools', repo_info['meta'])
    info['repoUrl'] = None
    info['toolchainUrl'] = None
    info['revision'] = None
    info['worktree'] = False

    rc = run_shell_cmd_with_output(CMD_GET_MANIFEST_PATH)
    if rc.returncode == 0:
        manifest_path = rc.stdout.strip()
        manifest_dir = os.path.join(sdkroot, NUWA_SDK_MANIFEST_DIR) + os.path.sep
        info['manifest'] = manifest_path.replace(manifest_dir, '')
        info['manifestDir'] = NUWA_SDK_MANIFEST_DIR
    else:
        raise RuntimeError('Fail to get manifest path: ' + rc.stderr)

    rc = run_shell_cmd_with_output(CMD_GET_MANIFEST_URL)
    if rc.returncode == 0:
        info['url'] = rc.stdout.strip()
    else:
        raise RuntimeError('Fail to get manifest url: ' + rc.stderr)

    if 'github' in info['url']:
        info['internal'] = False
    else:
        info['internal'] = True

    info['debuggerArgs'] = repo_info['debuggerArgs']
    info['overrideLaunchCommands'] = repo_info['overrideLaunchCommands']

    print(json.dumps(info, indent=4))


def main():
    parser = argparse.ArgumentParser(description=None)
    parser.add_argument('-a', '--app', action='store_true', help='show application information')
    parser.add_argument('-d', '--device', action='store_true', help='show device information')
    parser.add_argument('-i', '--info', action='store_true', help='show repository information')

    args = parser.parse_args()

    cfg = None
    if os.path.exists(NUWA_SDK_QUERY_CFG_FILE):
        try:
            with open(NUWA_SDK_QUERY_CFG_FILE, 'r') as f:
                cfg = json.load(f)
        except:
            raise RuntimeError('Error: Fail to load query configuration file "' + NUWA_SDK_QUERY_CFG_FILE + '"')
    else:
        raise RuntimeError('Error: Query configuration file "' + NUWA_SDK_QUERY_CFG_FILE + '" does not exist')

    # Meta tool should only run under SDK root directory
    sdkroot = os.getcwd()

    if args.app:
        do_query_app(sdkroot, cfg)
    elif args.device:
        do_query_device(cfg)
    elif args.info:
        do_query_info(sdkroot, cfg)
    else:
        parser.print_usage()
        raise RuntimeError('Warning: Invalid arguments')


if __name__ == '__main__':
    main()
