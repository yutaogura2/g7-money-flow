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


def test_parse_observations_filters_missing_and_sorts():
    payload = {"observations": [
        {"date": "2020-03-01", "value": "3.0"},
        {"date": "2020-01-01", "value": "1.0"},
        {"date": "2020-02-01", "value": "."},
    ]}
    rows = fetch_macro.parse_observations(payload)
    assert rows == [("2020-01-01", 1.0), ("2020-03-01", 3.0)]


def test_compute_yoy_matches_one_year_prior():
    rows = [(f"20{y:02d}-01-01", float(v)) for y, v in
            [(20, 100.0), (21, 110.0), (22, 121.0)]]
    out = fetch_macro.compute_yoy(rows)
    assert out[0] == ("2020-01-01", 100.0, None)   # 1年前なし
    assert out[1] == ("2021-01-01", 110.0, 10.0)   # +10%
    assert out[2] == ("2022-01-01", 121.0, 10.0)   # +10%


def test_to_csv_text_with_and_without_yoy():
    assert fetch_macro.to_csv_text([("2020-01-01", 1.0)], False) == "date,value\n2020-01-01,1.0\n"
    txt = fetch_macro.to_csv_text([("2020-01-01", 1.0, None), ("2021-01-01", 1.1, 10.0)], True)
    assert txt == "date,value,yoy_pct\n2020-01-01,1.0,\n2021-01-01,1.1,10.0\n"


def test_write_series_csv(tmp_path):
    fp = fetch_macro.write_series_csv("X", [("2020-01-01", 1.0)], False, data_dir=tmp_path)
    assert fp.exists()
    assert fp.read_text(encoding="utf-8") == "date,value\n2020-01-01,1.0\n"
