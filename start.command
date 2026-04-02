#!/bin/bash
# WattWise — Double-click to launch native app
cd "$(dirname "$0")"
echo "Starting WattWise..."
python3 macos/wattwise_app.py
