#!/bin/bash
# HeatSmart — Double-click to launch
cd "$(dirname "$0")"
echo "Starting HeatSmart..."
echo "Opening http://localhost:8000 in 3 seconds..."
sleep 3 && open http://localhost:8000 &
python3 -m uvicorn src.backend.main:app --host 127.0.0.1 --port 8000
