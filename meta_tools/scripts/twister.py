#! /usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (c) 2026 Realtek Semiconductor Corp.
# SPDX-License-Identifier: Apache-2.0

import argparse
import os
import subprocess
import sys
from pathlib import Path

import base.rtk_utils as utils

# zephyr/scripts/pylib/twister/twisterlib/environment.py uses `datetime.UTC`,
# which only exists from Python 3.11 onward.
MIN_PYTHON = (3, 11)

# Default JSON5 file describing named twister environments; see --config.
DEFAULT_CONFIG = Path(__file__).parent / "twister_envs.json5"


def dict_to_argv(merged):
    """Turn a merged (common + environment) dict into a west-twister argv.

    `name` is a label, not a CLI flag, and is skipped. Bool True emits the
    key alone (e.g. "--retry-build-errors": true -> ["--retry-build-errors"]);
    bool False omits the key entirely. A list value repeats "key value" once
    per item (e.g. "-p": ["a", "b"] -> ["-p", "a", "-p", "b"]).
    """
    argv = []
    for key, value in merged.items():
        if key == 'name':
            continue
        if isinstance(value, bool):
            if value:
                argv.append(key)
        elif isinstance(value, list):
            for item in value:
                argv.extend([key, str(item)])
        else:
            argv.extend([key, str(value)])
    return argv


def get_platforms(merged):
    """Extract the -p/--platform values (as a list) from a merged dict."""
    for key in ('-p', '--platform'):
        if key in merged:
            value = merged[key]
            return value if isinstance(value, list) else [value]
    return []


def resolve_and_set_toolchain(platforms):
    """Resolve the gnuarmemb toolchain for `platforms` and export it via env
    vars. Returns False (and prints an error) if the platforms need
    different toolchains, which a single twister run cannot use."""
    resolved = {p: utils.resolve_toolchain_path(p) for p in dict.fromkeys(platforms)}
    toolchain_paths = set(resolved.values())
    if len(toolchain_paths) > 1:
        print("Error: the requested platforms need different toolchains, "
              "which twister cannot use in a single run:")
        for p, path in resolved.items():
            print(f"  {p} -> {path}")
        return False

    os.environ['ZEPHYR_TOOLCHAIN_VARIANT'] = 'gnuarmemb'
    os.environ['GNUARMEMB_TOOLCHAIN_PATH'] = str(next(iter(toolchain_paths)))
    return True


def run_one(platforms, west_extra_argv):
    """Resolve toolchain for `platforms` and run `west twister` with
    `west_extra_argv` (already containing -p/--platform and everything
    else). Returns True/False instead of raising, so callers can run
    multiple environments without one failure aborting the rest."""
    if not resolve_and_set_toolchain(platforms):
        return False

    try:
        utils.run_west(["twister"] + west_extra_argv)
        return True
    except subprocess.CalledProcessError:
        return False


def run_from_config(config_path, env_names, remainder):
    try:
        import json5
    except ImportError:
        print("Error: the 'json5' package is required for --config "
              "(pip install -r tools/requirements.txt)")
        sys.exit(1)

    config_path = Path(config_path)
    if not config_path.exists():
        print(f"Error: config file not found: {config_path}")
        sys.exit(1)

    with open(config_path) as f:
        cfg = json5.load(f)

    common = cfg.get('common', {})
    environments = cfg.get('environments', [])
    if not environments:
        print(f"Error: no 'environments' entries found in {config_path}")
        sys.exit(1)

    matched_names = set()
    results = []
    for env in environments:
        name = env.get('name', '<unnamed>')
        if env_names and name not in env_names:
            continue
        matched_names.add(name)

        merged = dict(common)
        merged.update(env)

        platforms = get_platforms(merged)
        if not platforms:
            print(f"Error: environment '{name}' has no -p/--platform entry")
            sys.exit(1)

        print(f"\n{'=' * 70}\n>>> Environment: {name}\n{'=' * 70}")
        ok = run_one(platforms, dict_to_argv(merged) + remainder)
        results.append((name, ok))

    if env_names:
        missing = set(env_names) - matched_names
        if missing:
            print(f"Error: no environment(s) named: {', '.join(sorted(missing))}")
            sys.exit(1)

    print(f"\n{'=' * 70}\nSummary ({len(results)} environment(s)):")
    for name, ok in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")

    if not results or any(not ok for _, ok in results):
        sys.exit(1)


def main(argc, argv):
    if sys.version_info < MIN_PYTHON:
        print(
            "Error: twister requires Python {}.{}+ (this .venv is running "
            "Python {}.{}). Rebuild .venv with a newer interpreter, e.g. "
            "python3.11 -m venv --upgrade .venv".format(
                *MIN_PYTHON, sys.version_info.major, sys.version_info.minor
            )
        )
        sys.exit(1)

    # Forward straight to `west twister`'s own help instead of this wrapper's
    # (which only knows about -p/--config): it has ~100 options this wrapper
    # doesn't otherwise touch, and our own -h would shadow it.
    if '-h' in argv or '--help' in argv:
        utils.check_venv()
        result = utils.run_west(["twister", "-h"], check=False)
        sys.exit(result.returncode)

    parser = argparse.ArgumentParser(description=None)
    parser.add_argument('-p', '--platform', action='append',
                         help='platform to test; repeat for multiple platforms, '
                              'but they must all resolve to the same toolchain. '
                              'Not used together with --config.')
    parser.add_argument('--config', nargs='?', const=str(DEFAULT_CONFIG), default=None,
                         help='Path to a JSON5 file describing one or more named '
                              'twister environments (see twister_envs.json5 next '
                              'to this script for the schema); runs west twister '
                              'once per environment instead of once from -p. Bare '
                              f'--config (no path) uses {DEFAULT_CONFIG.name}.')
    parser.add_argument('--env', action='append', default=None,
                         help='With --config, only run environments whose "name" '
                              'is in this list (repeatable). Default: run all.')

    args, remainder = parser.parse_known_args(argv)

    utils.check_venv()

    if args.config:
        if args.platform:
            print("Error: --config and -p/--platform are mutually exclusive; "
                  "platforms come from each environment in the config file.")
            sys.exit(1)
        run_from_config(args.config, args.env, remainder)
        return

    if args.env:
        print("Error: --env only applies together with --config.")
        sys.exit(1)
    if not args.platform:
        print("Error: -p/--platform is required (or use --config).")
        sys.exit(1)

    west_extra_argv = []
    for p in args.platform:
        west_extra_argv.extend(["-p", p])
    west_extra_argv.extend(remainder)

    if not run_one(args.platform, west_extra_argv):
        sys.exit(1)


if __name__ == '__main__':
    main(len(sys.argv), sys.argv[1:])
