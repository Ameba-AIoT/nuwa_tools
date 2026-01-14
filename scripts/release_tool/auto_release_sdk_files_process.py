#!/usr/bin/env python3
import os
import shutil
import fnmatch
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_PATH = os.path.abspath(os.path.join(SCRIPT_DIR, "../../../"))
COPY_CMDS = {'d', 'dr', 'f', 'fr'}
DELETE_CMDS = {'dd', 'fd'}

# maxsize=n 表示最多缓存最近调用的 n 个结果，如果内存充足，也可以设大一点，或者设为 None (无限制缓存)
@lru_cache(maxsize=4096)
def cached_makedirs(path):
    """缓存目录创建操作，减少系统调用"""
    os.makedirs(path, exist_ok=True)

def normalize_path(path: str) -> str:
    """统一将路径中的反斜杠转为正斜杠，并移除开头的斜杠"""
    return os.path.normpath(path).replace("\\", "/").lstrip('/')

def copy_with_wildcard(src_dir: str, dst_dir: str, pattern: str):
    cached_makedirs(dst_dir)
    try:
        for name in os.listdir(src_dir):  # ← 仅当前目录，不递归
            full_path = os.path.join(src_dir, name)
            if os.path.isfile(full_path) and fnmatch.fnmatch(name, pattern):
                shutil.copy2(full_path, dst_dir)
    except FileNotFoundError:
        print(f"Warning: Source directory not found: {src_dir}")


def handle_copy_file(src_rel: str, dst_rel: str, out_dir: str):
    src = normalize_path(src_rel)
    dst = normalize_path(dst_rel)

    src_dir, src_base = os.path.split(src)
    dst_dir, dst_base = os.path.split(dst)

    src_full = os.path.join(ROOT_PATH, src)
    output_dst_dir = os.path.join(out_dir, dst_dir)

    if '*' in src_base:
        # 警告：通配时不支持重命名（多个文件无法映射到单个 dst_base）
        if dst_base != src_base:
            print(f"Warning: rename ignored for wildcard pattern: {src_rel} -> {dst_rel}")
        pattern = src_base
        walk_root = os.path.join(ROOT_PATH, src_dir) if src_dir else ROOT_PATH.rstrip('/')
        copy_with_wildcard(walk_root, output_dst_dir, pattern)
        return

    # 单文件复制
    if not os.path.isfile(src_full):
        print(f"Warning: File not found {src_full}")
        return

    cached_makedirs(output_dst_dir)
    dst_full = os.path.join(output_dst_dir, dst_base or src_base)
    shutil.copy2(src_full, dst_full)


def handle_copy_dir(src_rel: str, dst_rel: str, out_dir: str):
    src_norm = normalize_path(src_rel)
    dst_norm = normalize_path(dst_rel)
    src_full = os.path.join(ROOT_PATH, src_norm)
    dst_full = os.path.join(out_dir, dst_norm)

    if not os.path.isdir(src_full):
        print(f"Warning: Directory not found {src_full}")
        return

    if os.path.exists(dst_full):
        shutil.rmtree(dst_full)

    shutil.copytree(src_full, dst_full, ignore=shutil.ignore_patterns('.git', os.path.basename(out_dir)))


def get_command_target_path(parts):
    """
    解析命令，提取该命令操作的【目标路径】
    """
    cmd = parts[0]
    if cmd in ['f', 'd', 'fd', 'dd']:
        # 格式: cmd path
        return parts[1]
    elif cmd in ['fr', 'dr']:
        # 格式: cmd source target
        return parts[2]
    return ""

def process_all_files(file_list, out_dir):
    """
    读取所有文件 -> 解析命令 -> 按路径深度排序 -> 顺序执行
    """
    all_commands = []

    # 1. 读取所有文件的所有行
    for filename in file_list:
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    parts = line.split()
                    if not parts or parts[0].startswith((';', '#')):
                        continue

                    # 保存完整信息，用于后续执行
                    target_path = get_command_target_path(parts)
                    if target_path:
                        # 计算路径深度（斜杠的数量），作为排序依据
                        # normalize_path 确保 windows/linux 路径计算一致
                        depth = normalize_path(target_path).count('/')
                        all_commands.append({
                            'depth': depth,
                            'line': line,
                            'parts': parts,
                            'target_path': target_path
                        })
        except Exception as e:
            print(f"Error reading {filename}: {e}")

    # 2. 按路径深度排序 (从小到大)
    # 如果深度相同，保留原始文件里的相对顺序
    all_commands.sort(key=lambda x: x['depth'])

    # 3. 顺序执行
    for item in all_commands:
        parts = item['parts']
        cmd = parts[0]
        line = item['line']

        try:
            if cmd == "f":
                handle_copy_file(parts[1], parts[1], out_dir)
            elif cmd == "fr":
                handle_copy_file(parts[1], parts[2], out_dir)
            elif cmd == "d":
                handle_copy_dir(parts[1], parts[1], out_dir)
            elif cmd == "dr":
                handle_copy_dir(parts[1], parts[2], out_dir)

            elif cmd == "fd":
                target = os.path.join(out_dir, normalize_path(parts[1]))
                if os.path.isfile(target):
                    os.remove(target)

            elif cmd == "dd":
                target = os.path.join(out_dir, normalize_path(parts[1]))
                if os.path.isdir(target):
                    shutil.rmtree(target, ignore_errors=True)
            else:
                print(f"Unknown command: {cmd}")

        except Exception as e:
            print(f"Error processing '{line}': {e}")

def main():
    parser = argparse.ArgumentParser(description=None)
    parser.add_argument('--chip', required=True, help="The chip name (e.g., amebadplus, amebalite).")
    parser.add_argument('--out-dir', required=True, help="output directory.")
    args = parser.parse_args()

    chip = args.chip
    output_folder = args.out_dir

    file_list_common = os.path.join(SCRIPT_DIR, "auto_release_common.ini")
    file_list_chipdep = os.path.join(SCRIPT_DIR, f"{chip}/auto_release_{chip}_va0.ini")

    FILE_LISTS = [file_list_common, file_list_chipdep]

    process_all_files(FILE_LISTS, output_folder)


if __name__ == "__main__":
    main()
