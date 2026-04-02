"""py2app setup for WattWise native windowed app."""
from setuptools import setup

APP = ['wattwise_app.py']
OPTIONS = {
    'argv_emulation': False,
    'plist': {
        'CFBundleName': 'WattWise',
        'CFBundleDisplayName': 'WattWise',
        'CFBundleIdentifier': 'app.wattwise.desktop',
        'CFBundleVersion': '1.1.0',
        'CFBundleShortVersionString': '1.1.0',
        'LSUIElement': False,  # Native windowed app — show in Dock
        'NSHighResolutionCapable': True,
        'NSAppTransportSecurity': {
            'NSAllowsLocalNetworking': True,
        },
    },
    'packages': ['webview'],
}

setup(
    app=APP,
    name='WattWise',
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
