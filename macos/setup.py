"""py2app setup for HeatSmart menu bar app."""
from setuptools import setup

APP = ['heatsmart_menubar.py']
OPTIONS = {
    'argv_emulation': False,
    'plist': {
        'CFBundleName': 'HeatSmart',
        'CFBundleDisplayName': 'HeatSmart',
        'CFBundleIdentifier': 'app.heatsmart.menubar',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'LSUIElement': True,  # Menu bar app — no Dock icon
        'NSHighResolutionCapable': True,
    },
    'packages': ['rumps'],
}

setup(
    app=APP,
    name='HeatSmart',
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
