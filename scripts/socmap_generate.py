# 内部工具，用于对 SOC 映射关系进行混淆处理，生成 SOC_MAP_FILE

import json
import base64
import zlib
import math
import os

# update SOC mapping here. RTLxxx: project
# 料号大小写与在线文档保持一致
SOC_MAP = {
    "RTL872xD": "amebad",
    "RTL8721Dx": "amebadplus",
    "RTL8711Dx": "amebadplus",
    "RTL8730E": "amebasmart",
    "RTL8710E": "amebalite",
    "RTL8720E": "amebalite",
    "RTL8726E": "amebalite",
    "RTL8713E": "amebalite",
    "RTL8711F": "amebagreen2",
    "RTL8721F": "amebagreen2",
    "RTL8710F": "RTL8720F",
    "RTL8720F": "RTL8720F",
    "RTL8735C": "amebapro3"
}

SOC_MAP_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'soc_map.dat')

def data_obfuscation_save(output_path: str):
    """对数据进行混淆处理 并保存
    解析步骤必须完全相反. 对应ameba_soc_utils.py中的 _load_soc_map"""

    # 1. 将字典序列化为 JSON 字符串，然后编码为 UTF-8 字节流
    original_bytes = json.dumps(SOC_MAP, indent=4).encode('utf-8')

    # 2. 【第一步】: Zlib 压缩
    compressed_data = zlib.compress(original_bytes, level=9)

    # 3. 【第二步】: 自定义变换
    transformed_data = custom_transform(compressed_data)

    # 4. 【第三步】: Base64 编码
    final_obfuscated_content = base64.b64encode(transformed_data)

    # 5. 写入文件
    with open(output_path, 'wb') as f:
        f.write(final_obfuscated_content)

def custom_transform(data: bytes) -> bytes:
    """一个自定义的变换算法。
    解析步骤必须完全相反，对应ameba_soc_utils.py中的 _process_stream"""

    # 步骤1: 分成两半并交换
    midpoint = math.ceil(len(data) / 2)
    first_half = data[:midpoint]
    second_half = data[midpoint:]
    swapped_data = second_half + first_half

    # 步骤2: 位置相关异或
    xor_data = bytes([b ^ (i & 0xFF) for i, b in enumerate(swapped_data)])

    # 步骤3: 对每个字节执行固定的数学运算
    transformed_array = bytearray(xor_data)
    for i in range(len(transformed_array)):
        transformed_array[i] = (transformed_array[i] + 37) % 256

    return bytes(transformed_array)

if __name__ == "__main__":
    data_obfuscation_save(SOC_MAP_FILE)