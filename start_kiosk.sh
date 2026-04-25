#!/bin/bash
cd /home/orangepi/ww2_kiosk-main
source venv/bin/activate
export DISPLAY=:0
python src/main.py
