#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FRED からマクロ時系列を取得し macro_data/*.csv を生成する。"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SERIES_CONFIG = ROOT / "series_config.json"
API_KEY_FILE = ROOT / "fred_api_key.txt"
MACRO_DIR = ROOT / "macro_data"
FRED_URL = "https://api.stlouisfed.org/fred/series/observations"


def load_config(path: Path = SERIES_CONFIG) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_api_key(path: Path = API_KEY_FILE) -> str:
    p = Path(path)
    if not p.exists():
        raise SystemExit(
            f"FRED APIキーがありません。{p.name} に無料キーを1行で保存してください "
            f"(取得: https://fred.stlouisfed.org/docs/api/api_key.html)"
        )
    return p.read_text(encoding="utf-8").strip()
