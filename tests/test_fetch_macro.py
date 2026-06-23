import json
from pathlib import Path

import pytest

import fetch_macro


def test_load_config(tmp_path):
    p = tmp_path / "series_config.json"
    p.write_text(json.dumps({"history_points": 180, "series": [{"id": "M2SL"}]}), encoding="utf-8")
    cfg = fetch_macro.load_config(p)
    assert cfg["history_points"] == 180
    assert cfg["series"][0]["id"] == "M2SL"


def test_load_api_key_reads_and_strips(tmp_path):
    p = tmp_path / "fred_api_key.txt"
    p.write_text("  abcd1234\n", encoding="utf-8")
    assert fetch_macro.load_api_key(p) == "abcd1234"


def test_load_api_key_missing_raises(tmp_path):
    with pytest.raises(SystemExit):
        fetch_macro.load_api_key(tmp_path / "nope.txt")
