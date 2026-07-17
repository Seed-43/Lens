# config.py
#
# Copyright (C) 2026-present Seed-43
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

import os

# Application identity
APP_ID          = "io.github.seed43.lens"
RESOURCE_PREFIX = "/io/github/seed43/lens"

# Tessdata storage — respects XDG Base Directory spec
_xdg_data = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
tessdata_dir = os.path.join(_xdg_data, "tessdata")
os.makedirs(tessdata_dir, exist_ok=True)

# Tesseract model download URLs
tessdata_url      = "https://github.com/tesseract-ocr/tessdata/raw/main/"
tessdata_best_url = "https://github.com/tesseract-ocr/tessdata_best/raw/main/"

# Tesseract runtime config
tessdata_config = f"--tessdata-dir {tessdata_dir} --psm 3 --oem 1"
