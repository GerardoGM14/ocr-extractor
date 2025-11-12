# -*- mode: python ; coding: utf-8 -*-
# Archivo de especificación para PyInstaller
# Genera el .exe del procesador batch

import sys
from pathlib import Path

block_cipher = None

# PyInstaller incluirá automáticamente los módulos Python
added_files = []

a = Analysis(
    ['batch_entry.py'],
    pathex=[],
    binaries=[],
    datas=added_files,
    hiddenimports=[
        'google.generativeai',
        'google.api_core',
        'google.api_core.exceptions',
        'google.generativeai.types',
        'PIL',
        'PIL.Image',
        'fitz',
        'pymupdf',
        'pymupdf.fitz',
        'json',
        'pathlib',
        'concurrent.futures',
        'threading',
        'src',
        'src.core',
        'src.core.batch_processor',
        'src.core.file_manager',
        'src.core.ocr_extractor',
        'src.core.pdf_processor',
        'src.core.json_parser',
        'src.services',
        'src.services.gemini_service',
        'src.services.data_mapper',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ExtractorOCR_Batch',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

