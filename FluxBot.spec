# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_data_files

datas = [
    ('config.yaml', '.'),
    ('config.example.yaml', '.'),
    ('.env.example', '.'),
    ('README.md', '.'),
    ('NEWS_SOURCES.md', '.'),
    ('INSTALL.md', '.'),
    ('strategies', 'strategies'),
    ('assets/fluxbot.ico', 'assets'),
    ('assets/fluxbot_icon.png', 'assets'),
]
binaries = []
hiddenimports = [
    'ccxt',
    'customtkinter',
    'darkdetect',
    'yaml',
    'dotenv',
    'certifi',
    'app',
    'app.main',
    'app.engine',
    'app.paths',
    'app.config_loader',
    'app.exchange.binance_f',
    'app.strategy.trend',
    'app.news.sentiment',
    'app.risk.manager',
    'app.storage.db',
]

tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

try:
    datas += collect_data_files('certifi')
except Exception:
    pass

a = Analysis(
    ['run_fluxbot.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'scipy', 'PIL.ImageQt'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='FluxBot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon='assets/fluxbot.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='FluxBot',
)
