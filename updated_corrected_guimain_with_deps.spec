# updated_corrected_guimain_with_deps.spec

from PyInstaller.utils.hooks import collect_all, collect_submodules, get_package_paths
import os

# List of packages to collect
packages = [
    'telethon',
    'spacy',
    'pandas',
    'numpy',
    'customtkinter',
    'tkcalendar',
    'requests',
    'tkinter',
    'babel',
    'cryptography',
    'pyOpenSSL',
]

# Initialize lists to collect data files, binaries, and hidden imports
datas = []
binaries = []
hiddenimports = []

# Collect data files, binaries, and hidden imports for each package
for package in packages:
    pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hiddenimports

# Specifically handle 'babel' to ensure 'locale-data' is included correctly
babel_path = get_package_paths('babel')[1]
if os.path.exists(os.path.join(babel_path, 'locale-data')):
    datas += [(os.path.join(babel_path, 'locale-data'), 'babel/locale-data')]

# Include any additional data files required by your application
datas += [
    ('updated_updated_scraper.py', '.'),
    ('updated_updated_main.py', '.'),
    ('updated_video_transcription.py', '.'),
    ('updated_fetch_important_topics.py', '.'),
    ('selected_groups.txt', '.'),
    ('selected_data_types.txt', '.'),
    ('selected_date.txt', '.')
]

a = Analysis(
    ['updated_corrected_guimain_with_deps.py'],
    pathex=[os.path.abspath('.')],  # Add your project path
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

# Generate a separate .exe for the scraper
scraper_exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='updated_updated_scraper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Set to False if no console window is required
    disable_windowed_traceback=False,
)

# The main GUI .exe
gui_exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='updated_corrected_guimain_with_deps',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Set to False if no console window is required
    disable_windowed_traceback=False,
)

coll = COLLECT([gui_exe, scraper_exe], a.binaries, strip=False, upx=True, name='combined')
