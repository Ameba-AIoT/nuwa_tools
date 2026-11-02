#!/usr/bin/env python3
#
# Copyright (c) 2026 Realtek Semiconductor Corp.
# SPDX-License-Identifier: Apache-2.0
#
# Sync Ameba HAL sources, usrcfg and prebuilt blobs from a local Realtek SDK
# into nuwa. Nothing is committed; the changes land in two repos:
#   modules/hal/realtek/ameba   HAL sources, usrcfg
#   modules/hal/realtek         blobs (zephyr/blobs)
#
# * Sources: only files nuwa already has are overwritten; CMakeLists.txt and
#   Kconfig are never touched, nor are the files in KEEP_NUWA. A file nuwa has
#   that the SDK removed is an error.
#   The common/ trees in COMMON_TREES are shared by all boards and synced on
#   every run, whatever -b selects.
# * Blobs: the SDK is built twice with the Zephyr kernel, coex=n then coex=y
#   (the SDK default, so it is left as found), and its config is restored.

import argparse
import filecmp
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


def _workspace_root() -> Path:
    """Nearest ancestor holding .west/ -- the west workspace topdir."""
    here = Path(__file__).resolve()
    for d in (here, *here.parents):
        if (d / ".west").is_dir():
            return d
    sys.exit("error: not inside a west workspace (no .west/ found); "
             "run this from the nuwa workspace")


WS_ROOT = _workspace_root()
HAL_ROOT = WS_ROOT / "modules" / "hal" / "realtek"
AMEBA_ROOT = HAL_ROOT / "ameba"
BLOBS_ROOT = HAL_ROOT / "zephyr" / "blobs" / "ameba"

# NOT CONFIG_BT_COEXIST: that one is prompt-less and always reads n at top level.
COEX_SYMBOL = "CONFIG_COEX_MENU"
ZEPHYR_SYMBOL = "CONFIG_PLATFORM_ZEPHYR"

# nuwa board -> SDK soc dir (under component/soc/), SoC name, build dir.
BOARDS = {
    "amebasmart": {"soc": "amebasmart",  "soc_name": "RTL8730E",
                   "build_dir": "build_RTL8730E"},
    "amebadplus": {"soc": "amebadplus",  "soc_name": "RTL8721Dx",
                   "build_dir": "build_RTL8721Dx"},
    "amebag2":    {"soc": "amebagreen2", "soc_name": "RTL8721F",
                   "build_dir": "build_RTL8721F"},
}

# Where each nuwa blob comes from.
#   libs   : (nuwa path, path under <sdk>)
#   images : (nuwa path, path under <sdk>/<build_dir>, COEX_SAME | COEX_DIFFERS)
# A COEX_DIFFERS image is shipped twice: as-is from the coex=n build, and as
# *_coex.bin from the coex=y build.
COEX_SAME = False
COEX_DIFFERS = True

_SMART_AP_APP = "component/soc/amebasmart/project/project_ap/lib/application"
_SMART_AP_SOC = "component/soc/amebasmart/project/project_ap/lib/soc"
_SMART_HP = "component/soc/amebasmart/project/project_hp"
_DPLUS_KM4 = "component/soc/amebadplus/project/project_km4"
_DPLUS_KM4_APP = f"{_DPLUS_KM4}/lib/application"
_G2_KM4TZ = "component/soc/amebagreen2/project/project_km4tz"
_G2_KM4TZ_APP = f"{_G2_KM4TZ}/lib/application"

BLOB_MANIFEST = {
    "amebasmart": {
        "libs": [
            # WiFi / WHC / coex, linked by amebasmart/CMakeLists.txt (AP = CA32).
            *[(f"lib/{lib}", f"{_SMART_AP_APP}/{lib}") for lib in (
                "lib_coex_api.a", "lib_rtw_event.a",
                "lib_whc_ap.a", "lib_wifi_api.a", "lib_wifi_com_sec.a",
                "lib_wifi_rtk_app.a", "lib_wifi_whc_ipc_host.a", "lib_wpa_lite.a",
            )],
            # SoC libs (AP core). libpm.a is linked by tf-a (BL32), the rest by
            # amebasmart/CMakeLists.txt.
            *[(f"lib/{lib}", f"{_SMART_AP_SOC}/{lib}") for lib in (
                "lib_chipinfo.a", "lib_rom.a", "lib_pmc.a", "libpm.a",
            )],
            # The KM4 core builds its own lib_chipinfo.a; nuwa links both.
            ("lib/km4/lib_chipinfo.a", f"{_SMART_HP}/lib/soc/lib_chipinfo.a"),
            ("bin/floader_amebasmart.bin",
             f"{_SMART_HP}/gnu_utility/image_tool_flashloader/amebasmart_acut/"
             "floader_amebasmart.bin"),
        ],
        "images": [
            # KM0 runs on the LP core, so its image is built in project_lp.
            ("bin/km0_image2_all.bin", "build/project_lp/image/km0_image2_all.bin", COEX_SAME),
            # The KM4 bootloader; the SDK publishes it as <build_dir>/boot.bin.
            ("bin/km4_boot_all.bin",   "boot.bin",                                  COEX_SAME),
            ("bin/km4_image2_all.bin", "build/project_hp/image/km4_image2_all.bin", COEX_DIFFERS),
        ],
    },
    "amebadplus": {
        "libs": [
            # WiFi / WHC / coex, linked by amebadplus/CMakeLists.txt (AP = KM4).
            # lib_usbd.a is left to the USB owner, paired with common/usb.
            *[(f"lib/{lib}", f"{_DPLUS_KM4_APP}/{lib}") for lib in (
                "lib_coex_api.a", "lib_rtw_event.a", "lib_whc_ap.a",
                "lib_wifi_api.a", "lib_wifi_com_sec.a", "lib_wifi_rtk_app.a",
                "lib_wifi_whc_ipc_host.a", "lib_wpa_lite.a",
            )],
            # SoC libs, KM4 core.
            *[(f"lib/{lib}", f"{_DPLUS_KM4}/lib/soc/{lib}") for lib in (
                "lib_bootloader.a", "lib_chipinfo.a", "lib_pmc.a",
            )],
            ("bin/floader_amebadplus.bin",
             f"{_DPLUS_KM4}/gnu_utility/image_tool_flashloader/amebadplus_acut/"
             "floader_amebadplus.bin"),
        ],
        "images": [
            # Coex links into KM0 on dplus.
            ("bin/km0_image2_all.bin", "build/project_km0/image/km0_image2_all.bin", COEX_DIFFERS),
            # The KM4 bootloader; the SDK publishes it as <build_dir>/boot.bin.
            ("bin/km4_boot_all.bin",   "boot.bin",                                   COEX_SAME),
        ],
    },
    "amebag2": {
        "libs": [
            # WiFi / WHC / coex, linked by amebag2/CMakeLists.txt (AP = KM4TZ).
            # lib_usbd.a and lib_usbh.a are left to the USB owner, paired with common/usb.
            *[(f"lib/{lib}", f"{_G2_KM4TZ_APP}/{lib}") for lib in (
                "lib_coex_api.a", "lib_rtw_event.a", "lib_whc_ap.a",
                "lib_wifi_api.a", "lib_wifi_common.a", "lib_wifi_rtk_app.a",
                "lib_wifi_whc_ipc_host.a", "lib_wpa_lite.a",
            )],
            # SoC libs, KM4TZ core.
            *[(f"lib/{lib}", f"{_G2_KM4TZ}/lib/soc/{lib}") for lib in (
                "lib_bootloader.a", "lib_chipinfo.a", "lib_pmc.a",
            )],
            ("bin/floader_amebagreen2.bin",
             f"{_G2_KM4TZ}/gnu_utility/image_tool_flashloader/amebagreen2_acut/"
             "floader_amebagreen2.bin"),
        ],
        "images": [
            # The KM4TZ bootloader; the SDK publishes it as <build_dir>/boot.bin.
            ("bin/amebagreen2_boot.bin", "boot.bin", COEX_SAME),
            # Coex links into KM4NS (the NP) on g2.
            ("bin/km4ns_image2_all.bin", "build/project_km4ns/image/km4ns_image2_all.bin", COEX_DIFFERS),
        ],
    },
}


# --------------------------------------------------------------------------- #
# Change detection
# --------------------------------------------------------------------------- #

# The bootloader embeds __DATE__/__TIME__.
_TIME_RE = re.compile(rb"\b\d{2}:\d{2}:\d{2}\b")
_DATE_RE = re.compile(rb"\b[A-Z][a-z]{2} [ \d]\d \d{4}\b")


def stable_hash(path: Path) -> str:
    """Content hash ignoring what changes on every rebuild: `ar` member
    timestamps and the bootloader's build date/time.
    """
    if path.suffix == ".a":
        try:
            res = subprocess.run(["ar", "p", str(path)], capture_output=True)
            if res.returncode == 0:
                return hashlib.sha256(res.stdout).hexdigest()
        except (OSError, subprocess.SubprocessError):
            pass  # fall through to raw bytes
        return hashlib.sha256(path.read_bytes()).hexdigest()
    data = path.read_bytes()
    data = _TIME_RE.sub(b"HH:MM:SS", data)
    data = _DATE_RE.sub(b"Mmm DD YYYY", data)
    return hashlib.sha256(data).hexdigest()


def copy_file(src: Path, dst: Path, apply: bool) -> str:
    """Copy src->dst if the content really differs; returns "missing",
    "unchanged" or "updated"."""
    if not src.is_file():
        return "missing"
    if dst.exists() and (filecmp.cmp(src, dst, shallow=False)
                         or stable_hash(src) == stable_hash(dst)):
        return "unchanged"
    if apply:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return "updated"


def report(label: str, updated, missing=(), apply=True) -> bool:
    """One summary line, then the changed files and any errors."""
    if updated:
        print(f"{label}: {len(updated)} " + ("updated" if apply else "to be updated"))
    else:
        print(f"{label}: up to date")
    for rel in updated:
        print(f"    {rel}")
    for rel in missing:
        print(f"    [ERROR] missing in SDK: {rel}")
    return not missing


# --------------------------------------------------------------------------- #
# SDK interaction
# --------------------------------------------------------------------------- #

SDK_ENV = None  # set by load_sdk_env()


def load_sdk_env(sdk_root: Path) -> bool:
    """Source the SDK's env.sh once (prebuilts PATH, SDK venv) and keep it."""
    global SDK_ENV
    res = subprocess.run(["bash", "-c", "source ./env.sh >&2 && env -0"],
                         cwd=str(sdk_root), capture_output=True, text=True)
    env = dict(kv.split("=", 1) for kv in res.stdout.split("\0") if "=" in kv)
    if res.returncode != 0 or "VIRTUAL_ENV" not in env:
        print(res.stderr.rstrip(), file=sys.stderr)
        print(f"error: `source {sdk_root}/env.sh` failed", file=sys.stderr)
        return False
    SDK_ENV = env
    return True


def run_ameba(sdk_root: Path, extra, capture=False):
    """Run the SDK's ameba.py in the env.sh environment."""
    return subprocess.run(["python", "ameba.py", *extra], env=SDK_ENV,
                          cwd=str(sdk_root), text=True, capture_output=capture)


def _first_json(text: str):
    for line in (text or "").splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return None


def current_soc(sdk_root: Path):
    """SoC name currently selected in the SDK (from soc_info.json)."""
    try:
        data = json.loads((sdk_root / "soc_info.json").read_text())
        return data.get("soc", {}).get("name")
    except (OSError, json.JSONDecodeError):
        return None


def select_soc(sdk_root: Path, soc_name: str) -> bool:
    """`ameba.py soc <name>` - persists the choice in soc_info.json."""
    return run_ameba(sdk_root, ["soc", soc_name], capture=True).returncode == 0


def get_config(sdk_root: Path, soc_name: str, symbol: str):
    """Value of `symbol`, or None. Also selects soc_name in the SDK."""
    res = run_ameba(sdk_root, ["menuconfig", soc_name, "--get", symbol],
                    capture=True)
    data = _first_json(res.stdout)
    if data and data.get("success"):
        return data.get("values", {}).get(symbol)
    return None


def set_config(sdk_root: Path, soc_name: str, symbol: str, value: str) -> bool:
    res = run_ameba(sdk_root,
                    ["menuconfig", soc_name, "--set", f"{symbol}={value}"],
                    capture=True)
    data = _first_json(res.stdout)
    return bool(data and data.get("success"))


# --------------------------------------------------------------------------- #
# Source trees
# --------------------------------------------------------------------------- #

# Same name on both sides, but different build systems.
_NEVER_SYNC = {"CMakeLists.txt", "Kconfig"}

# Files that knowingly differ from the SDK and must keep nuwa's copy:
# path under modules/hal/realtek/ameba -> why. Each one is reported on every
# run; drop the entry once the file is reconciled with the SDK.
KEEP_NUWA = {
    "usrcfg/amebadplus/ameba_boot_trustzonecfg.c":
        "TF-M BL2 MPC config, the SDK copy is the FreeRTOS SAU config",
    "usrcfg/amebag2/ameba_boot_trustzonecfg.c":
        "TF-M BL2 MPC config, the SDK copy is the FreeRTOS SAU config",
}

# Shared by all boards: nuwa dir under modules/hal/realtek/ameba -> dir under <sdk>.
COMMON_TREES = [
    ("common/at_cmd",             "component/at_cmd"),
    ("common/crashdump/include",  "component/soc/common/crashdump/include"),
    ("common/include",            "component/soc/common/include"),
    ("common/os_wrapper/include", "component/os/os_wrapper/include"),
    ("common/rtk_coex/source",    "component/rtk_coex"),
]
# Not synced here:
#   common/usb and lib_usbd.a/lib_usbh.a: maintained by the USB owner as a pair.
#   common/bluetooth: still carries Zephyr changes the SDK lacks; add it back
#   ("common/bluetooth", "component/bluetooth") once the BT owner merges them.


def sdk_removed(sdk_dir: Path, rels) -> list:
    """Of the files the SDK lacks, those its git history once had (removed or
    renamed); the rest are nuwa's own."""
    rels = list(rels)
    if not rels:
        return []
    res = subprocess.run(
        ["git", "log", "--format=", "--name-only", "--relative", "--", *map(str, rels)],
        cwd=str(sdk_dir), text=True, capture_output=True)
    if res.returncode != 0:
        print(f"    [ERROR] git log failed in {sdk_dir}: {res.stderr.strip()}")
        return rels
    seen = set(res.stdout.split())
    return [r for r in rels if str(r) in seen]


def sync_tree(label: str, nuwa_dir: Path, sdk_dir: Path, apply: bool) -> bool:
    """Overwrite each file nuwa has with the SDK's copy at the same path."""
    if not nuwa_dir.is_dir():
        return True
    if not sdk_dir.is_dir():
        print(f"{label}: [ERROR] SDK path missing: {sdk_dir}")
        return False

    updated, absent, kept = [], [], []
    for path in sorted(nuwa_dir.rglob("*")):
        if not path.is_file() or path.name in _NEVER_SYNC:
            continue
        rel = path.relative_to(nuwa_dir)
        why = KEEP_NUWA.get(str(path.relative_to(AMEBA_ROOT)))
        if why:
            kept.append(f"{rel} ({why})")
            continue
        src = sdk_dir / rel
        if not src.is_file():
            absent.append(rel)
        elif not filecmp.cmp(src, path, shallow=False):
            updated.append(rel)
            if apply:
                shutil.copy2(src, path)
    ok = report(label, updated, sdk_removed(sdk_dir, absent), apply)
    for rel in kept:
        print(f"    [KEPT] nuwa copy: {rel}")
    return ok


def sync_source(board: str, sdk_root: Path, apply: bool) -> bool:
    return sync_tree(f"{board} source",
                     AMEBA_ROOT / board / "source",
                     sdk_root / "component" / "soc" / BOARDS[board]["soc"],
                     apply)


def sync_usrcfg(board: str, sdk_root: Path, apply: bool) -> bool:
    return sync_tree(f"{board} usrcfg",
                     AMEBA_ROOT / "usrcfg" / board,
                     sdk_root / "component" / "soc" / "usrcfg"
                     / BOARDS[board]["soc"],
                     apply)


def sync_common(sdk_root: Path, apply: bool) -> bool:
    ok = True
    for nuwa_rel, sdk_rel in COMMON_TREES:
        ok = sync_tree(nuwa_rel, AMEBA_ROOT / nuwa_rel, sdk_root / sdk_rel,
                       apply) and ok
    return ok


# --------------------------------------------------------------------------- #
# Blobs
# --------------------------------------------------------------------------- #

def sync_libs(board: str, sdk_root: Path, apply: bool) -> bool:
    dst_root = BLOBS_ROOT / board
    updated, missing = [], []
    for nuwa_rel, sdk_rel in BLOB_MANIFEST[board]["libs"]:
        st = copy_file(sdk_root / sdk_rel, dst_root / nuwa_rel, apply)
        if st == "updated":
            updated.append(nuwa_rel)
        elif st == "missing":
            missing.append(sdk_rel)
    return report(f"{board} libs", updated, missing)


def collect_images(board: str, sdk_root: Path, coex: bool, apply: bool) -> bool:
    """Copy the images of the build just made: coex=n takes only the
    COEX_DIFFERS ones; coex=y takes the rest, plus COEX_DIFFERS as *_coex.bin."""
    build_dir = sdk_root / BOARDS[board]["build_dir"]
    dst_root = BLOBS_ROOT / board
    updated, missing = [], []
    for nuwa_rel, build_rel, differs in BLOB_MANIFEST[board]["images"]:
        if not coex and not differs:
            continue
        dst_rel = nuwa_rel
        if coex and differs:  # km4_image2_all.bin -> km4_image2_all_coex.bin
            p = Path(nuwa_rel)
            dst_rel = str(p.with_name(p.stem + "_coex" + p.suffix))
        st = copy_file(build_dir / build_rel, dst_root / dst_rel, apply)
        if st == "updated":
            updated.append(dst_rel)
        elif st == "missing":
            missing.append(f"{BOARDS[board]['build_dir']}/{build_rel}")
    return report(f"{board} images (coex={'y' if coex else 'n'})", updated, missing)


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

def build_blobs(board: str, sdk_root: Path, apply: bool) -> bool:
    """Build the SDK twice, collect the blobs, restore the SDK's config."""
    soc_name = BOARDS[board]["soc_name"]
    libs = BLOB_MANIFEST[board]["libs"]
    images = BLOB_MANIFEST[board]["images"]
    if not libs and not images:
        print(f"{board} blobs: skipped, BLOB_MANIFEST not populated")
        return True

    if not apply:
        # Images only exist once built; check the lib sources only.
        nbins = len(images) + sum(1 for *_, differs in images if differs)
        print(f"{board} blobs: would build the SDK twice (coex=n, coex=y) and "
              f"copy {len(libs)} libs + {nbins} bins")
        missing = [src for _dst, src in libs if not (sdk_root / src).is_file()]
        for src in missing:
            print(f"    [ERROR] missing in SDK: {src}")
        return not missing

    prev_soc = current_soc(sdk_root)
    orig_coex = get_config(sdk_root, soc_name, COEX_SYMBOL)
    orig_zephyr = get_config(sdk_root, soc_name, ZEPHYR_SYMBOL)
    if orig_coex is None or orig_zephyr is None:
        print(f"{board} blobs: [ERROR] cannot read {COEX_SYMBOL}/{ZEPHYR_SYMBOL}")
        if prev_soc and prev_soc != soc_name:
            select_soc(sdk_root, prev_soc)
        return False

    ok = True
    if not select_soc(sdk_root, soc_name):
        print(f"{board} blobs: [ERROR] `ameba.py soc {soc_name}` failed")
        return False
    try:
        if not set_config(sdk_root, soc_name, ZEPHYR_SYMBOL, "y"):
            print(f"{board} blobs: [ERROR] cannot set {ZEPHYR_SYMBOL}=y")
            return False
        # coex=y last: the SDK default, and the build that produces the libs.
        for coex in (False, True):
            val = "y" if coex else "n"
            print(f"{board} blobs: building the SDK with {COEX_SYMBOL}={val} ...",
                  flush=True)
            if not set_config(sdk_root, soc_name, COEX_SYMBOL, val):
                print(f"    [ERROR] cannot set {COEX_SYMBOL}={val}")
                ok = False
                break
            if run_ameba(sdk_root, ["build"]).returncode != 0:
                print("    [ERROR] SDK build failed")
                ok = False
                break
            ok = collect_images(board, sdk_root, coex, apply=True) and ok
            if coex:
                ok = sync_libs(board, sdk_root, True) and ok
    finally:
        set_config(sdk_root, soc_name, COEX_SYMBOL, orig_coex)
        set_config(sdk_root, soc_name, ZEPHYR_SYMBOL, orig_zephyr)
        if prev_soc and prev_soc != soc_name:
            select_soc(sdk_root, prev_soc)
        if orig_coex != "y" or orig_zephyr != "y":
            print("    note: the SDK build dir no longer matches its restored "
                  "config; re-run `ameba.py build` there to realign it")

    return ok


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync Ameba HAL sources, usrcfg, and blobs from two fresh "
                    "SDK builds, from a local SDK into nuwa.",
    )
    parser.add_argument("-s", "--sdk", type=Path, required=True,
                        help="Path to the Ameba SDK checkout (required).")
    parser.add_argument("-b", "--board", action="append", choices=sorted(BOARDS),
                        help="Board to sync (repeatable). Default: all boards.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would change; write nothing and run no "
                             "SDK build.")
    args = parser.parse_args()

    sdk_root = args.sdk.expanduser().resolve()
    if not (sdk_root / "ameba.py").is_file():
        print(f"error: {sdk_root} does not look like an Ameba SDK (no ameba.py)",
              file=sys.stderr)
        return 2
    for label, path in (("HAL sources", AMEBA_ROOT), ("blobs", BLOBS_ROOT)):
        if not path.is_dir():
            print(f"error: {label} not found at {path}; is the workspace "
                  "initialised (`west update`)?", file=sys.stderr)
            return 2

    apply = not args.dry_run
    if apply and not load_sdk_env(sdk_root):
        return 2
    print(f"SDK: {sdk_root}"
          + ("" if apply else "   (DRY-RUN, nothing is written or built)"))

    ok = sync_common(sdk_root, apply)
    for board in args.board or list(BOARDS):
        ok = sync_source(board, sdk_root, apply) and ok
        ok = sync_usrcfg(board, sdk_root, apply) and ok
        ok = build_blobs(board, sdk_root, apply) and ok

    print("\nCheck before commit:")
    print(f"  - git -C {AMEBA_ROOT.relative_to(WS_ROOT)} diff: nuwa patches "
          "overwritten by the SDK?")
    print(f"  - git -C {HAL_ROOT.relative_to(WS_ROOT)} diff: blobs as expected?")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
