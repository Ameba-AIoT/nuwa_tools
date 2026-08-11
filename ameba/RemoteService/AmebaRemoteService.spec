# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path
sys.path.insert(0, str((Path("__name__").parent)))
from tempfile import  NamedTemporaryFile
from version_manager import version
from AmebaRemoteService import APP_NAME

file_name = f"{APP_NAME}"
file_version = f"{version}.0"
temp_version_file=Path("version.tmp")
temp_version_file.write_text(
f"""# UTF-8 encoding
# UTF-8
#
# Fields to define the version info for a Windows executable
VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=({file_version.replace(".",",")}),       # 文件版本号
        prodvers=({file_version.replace(".",",")}),       # 产品版本号
        mask=0x3f,
        flags=0x0,
        OS=0x40004,
        fileType=0x1,
        subtype=0x0,
        date=(0, 0)
        ),
    kids=[
        StringFileInfo(
        [
        StringTable(
            u'040904B0',
            [StringStruct(u'CompanyName', u'Realtek Semiconductor Corp.'),
            StringStruct('FileDescription', 'Ameba remote service'),
            StringStruct(u'FileVersion', u'{version}'),
            StringStruct('InternalName', '{file_name}.exe'),
            StringStruct(u'LegalCopyright', u'Copyright (c) 2025 Realtek Semiconductor Corp.'),
            StringStruct('OriginalFilename', '{file_name}.exe'),
            StringStruct('ProductName', '{file_name}'),
            StringStruct(u'ProductVersion', u'{version}')])
        ]),
        VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
    ]
)
""",encoding='utf-8')


a = Analysis(
    ['AmebaRemoteService.py', 'version_manager.py'],
    pathex=[],
    binaries=[],
    datas=[('realtek.ico', '.'),
        ('xpack-openocd-0.12.0-7-win32-x64', 'xpack-openocd-0.12.0-7-win32-x64'), 
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=f'{file_name}_v{version}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    uac_admin=False,
    codesign_identity=None,
    entitlements_file=None,
    icon=['realtek.ico'],
    version=temp_version_file.name,
)
os.remove(temp_version_file.name)