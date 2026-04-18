# config.py
#
# Copyright 2021-2025 Andrey Maksimov
# Copyright 2026-present Seed-43
#
# MIT License - see LICENSE file for details

import os

APP_ID = "io.github.seed43.lens"
RESOURCE_PREFIX = "/io/github/seed43/lens"

# XDG Base Directory specification
if not os.getenv('XDG_DATA_HOME'):
    os.environ['XDG_DATA_HOME'] = os.path.expanduser('~/.local/share')

if not os.path.exists(os.path.join(os.environ['XDG_DATA_HOME'], 'tessdata')):
    os.mkdir(os.path.join(os.environ['XDG_DATA_HOME'], 'tessdata'))

tessdata_url = "https://github.com/tesseract-ocr/tessdata/raw/main/"
tessdata_best_url = "https://github.com/tesseract-ocr/tessdata_best/raw/main/"
tessdata_dir = os.path.join(os.environ['XDG_DATA_HOME'], 'tessdata')
tessdata_config = f'--tessdata-dir {tessdata_dir} --psm 3 --oem 1'
