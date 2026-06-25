# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('app/assets', 'app/assets'),
    ] + collect_data_files('customtkinter'),
    hiddenimports=collect_submodules('customtkinter') + [
        'PIL._tkinter_finder',
        'pillow_heif',
        'open_clip',
        'imagehash',
        'keyring',
        'keyring.backends',
        'keyring.backends.macOS',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='MemoryBox',
    debug=False,
    console=False,
)

coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name='MemoryBox')

app = BUNDLE(
    coll,
    name='MemoryBox.app',
    icon='app/assets/icon.icns',
    bundle_identifier='com.arpitjaiswal.memorybox',
    info_plist={
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '12.0',
    }
)
