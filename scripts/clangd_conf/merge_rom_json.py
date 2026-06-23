import json
import os
import re
import sys


def _get_compiler_name(path):
    """从完整路径中提取编译器名，如 /path/to/arm-none-eabi-gcc -> arm-none-eabi-gcc"""
    return os.path.basename(path.strip())


def build_compiler_map(main_db):
    """
    遍历主 compile_commands.json，建立 {编译器名 -> 完整编译器路径} 的映射。

    例如:
        "arm-none-eabi-gcc"  -> "/home/user/.../bin/arm-none-eabi-gcc"
        "riscv32-none-elf-gcc" -> "/home/user/.../bin/riscv32-none-elf-gcc"
    """
    compiler_map = {}
    compiler_pattern = re.compile(r'(gcc|g\+\+|clang|clang\+\+|cc)\S*$')
    for entry in main_db:
        cmd = entry.get("command", "")
        if not cmd:
            continue
        first_token = cmd.split(maxsplit=1)[0].strip()
        if compiler_pattern.search(first_token):
            name = _get_compiler_name(first_token)
            if name not in compiler_map:
                compiler_map[name] = first_token
    return compiler_map


def replace_compiler_dir_placeholder(rom_db, local_compiler_map):
    """
    将 ROM 条目 command 中的 __COMPILER_DIR__ 占位符替换为本地编译器目录。

    对于 command 形如:
        __COMPILER_DIR__/arm-none-eabi-gcc -I...
    根据 local_compiler_map 中对应的完整路径，提取目录部分替换。

    Returns:
        int: 替换的条目数
    """
    # 建立 {编译器名 -> 目录} 映射
    local_compiler_dir_map = {}
    for compiler_name, full_path in local_compiler_map.items():
        local_compiler_dir_map[compiler_name] = os.path.dirname(full_path)

    if not local_compiler_dir_map:
        return 0

    replaced = 0
    for entry in rom_db:
        cmd = entry.get("command", "")
        if "__COMPILER_DIR__" not in cmd:
            continue

        # 查找 command 中 __COMPILER_DIR__ 后面跟的是哪个编译器
        for compiler_name, local_dir in local_compiler_dir_map.items():
            old_pattern = f"__COMPILER_DIR__/{compiler_name}"
            if old_pattern in cmd:
                entry["command"] = cmd.replace(old_pattern,
                                               f"{local_dir}/{compiler_name}", 1)
                replaced += 1
                break
        else:
            m = re.search(r'__COMPILER_DIR__/(\S+)', cmd)
            if m:
                print(f"[ROM JSON Merge] Warning: Unknown compiler "
                      f"'{m.group(1)}' for __COMPILER_DIR__ replacement")

    return replaced


def merge_json(main_json_path, soc_type_or_rom_path, basedir):
    # Check if soc_type_or_rom_path is a path ending with .json
    if soc_type_or_rom_path.endswith('.json'):
        rom_json_path = soc_type_or_rom_path
    else:
        soc_type = soc_type_or_rom_path
        out_name_map = {
            "amebasmart": "RTL8730E_Rom.json",
            "amebalite": "RTL8720E_Rom.json",
            "amebadplus": "RTL8721Dx_Rom.json",
            "amebagreen2": "RTL8721F_Rom.json",
            "RTL8720F": "RTL8720F_Rom.json"
        }
        rom_json_name = out_name_map.get(soc_type, f"{soc_type}_Rom.json")
        rom_json_path = os.path.join(basedir, "tools", "scripts", "clangd_conf", rom_json_name)

    if not os.path.exists(main_json_path):
        return
    if not os.path.exists(rom_json_path):
        return

    with open(main_json_path, 'r') as f:
        main_db = json.load(f)

    # 读取 ROM JSON，将占位符替换为当前环境的实际路径
    with open(rom_json_path, 'r') as f:
        rom_content = f.read()
        rom_content = rom_content.replace("__BASEDIR__", basedir)
        rom_db = json.loads(rom_content)

    # ---- 替换 __COMPILER_DIR__ 占位符为本地编译器目录 ----
    local_compiler_map = build_compiler_map(main_db)
    replaced = replace_compiler_dir_placeholder(rom_db, local_compiler_map)
    if replaced > 0:
        print(f"[ROM JSON Merge] Replaced __COMPILER_DIR__ for {replaced} entries.")
    else:
        has_placeholder = any("__COMPILER_DIR__" in e.get("command", "")
                              for e in rom_db)
        if has_placeholder:
            print(f"[ROM JSON Merge] Warning: __COMPILER_DIR__ found but could not be "
                  f"resolved. local_compiler_map={local_compiler_map}")

    # 去重：避免对同一文件的重复条目
    existing_files = {entry.get("file") for entry in main_db if "file" in entry}

    added = 0
    for rom_entry in rom_db:
        if "file" in rom_entry and rom_entry["file"] not in existing_files:
            main_db.append(rom_entry)
            added += 1

    if added > 0:
        with open(main_json_path, 'w') as f:
            json.dump(main_db, f, indent=2)
        print(f"[ROM JSON Merge] Added {added} ROM entries to compile_commands.json "
              f"from {os.path.basename(rom_json_path)}")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: merge_rom_json.py <main_json> <soc_type_or_rom_json> <basedir>")
        sys.exit(0)

    try:
        merge_json(sys.argv[1], sys.argv[2], sys.argv[3])
    except Exception as e:
        print(f"[ROM JSON Merge] Warning: Merge failed, but continuing build. ({e})")
        sys.exit(0)
