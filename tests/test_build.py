import json
import re
from pathlib import Path

import pytest

import build

SAMPLE = {
    "meta": {"last_updated": "2026-06-22", "sources": [], "disclaimer": "参考情報"},
    "meetings": [
        {
            "id": "m1", "date": "2025-05-22", "type": "財務相・中銀総裁会議",
            "presidency": "カナダ", "title_orig": "G7 FMCBG Statement",
            "title_ja": "G7財務相・中銀総裁声明", "source_url": "https://example.com/a",
            "source_lang": "en", "summary_ja": "要約A",
            "key_points_ja": ["決定1", "決定2"], "full_translation_ja": "全訳A",
            "analysis": {"fx_rates": "為替A", "commodities": "商品A",
                         "sectors": "セクターA", "geopolitics": "地政学A"},
            "market_direction": "リスクオフ", "tags": ["制裁", "為替"],
        }
    ],
    "calendar": [
        {"date": "2026-06-15", "name_ja": "G7首脳会議", "category": "G7首脳",
         "status": "予定", "related_meeting_id": None, "note": "議長国フランス"}
    ],
}


@pytest.fixture
def sample_json(tmp_path):
    p = tmp_path / "data.json"
    p.write_text(json.dumps(SAMPLE, ensure_ascii=False), encoding="utf-8")
    return p


def test_write_data_js_has_prefix_and_valid_json(tmp_path, sample_json):
    data = build.load_data(sample_json)
    out = tmp_path / "data.js"
    build.write_data_js(data, out)
    text = out.read_text(encoding="utf-8")
    assert text.startswith("window.G7DATA = ")
    body = re.sub(r"^window\.G7DATA = ", "", text).rstrip().rstrip(";")
    parsed = json.loads(body)
    assert parsed["meetings"][0]["title_ja"] == "G7財務相・中銀総裁声明"
    # 日本語がエスケープされず読めること
    assert "\\u" not in text


from openpyxl import load_workbook


def test_build_xlsx_sheets_and_rows(tmp_path, sample_json):
    data = build.load_data(sample_json)
    out = tmp_path / "out.xlsx"
    build.build_xlsx(data, out)
    wb = load_workbook(out)
    assert wb.sheetnames == ["会議ログ", "カレンダー", "考察サマリ", "マクロ_最新", "マクロ_時系列"]
    assert wb["会議ログ"].max_row == 2       # ヘッダ + 1会議
    assert wb["カレンダー"].max_row == 2      # ヘッダ + 1イベント
    assert wb["考察サマリ"].max_row == 5      # ヘッダ + 4観点
    # ヘッダ確認
    assert wb["会議ログ"].cell(row=1, column=1).value == "日付"


def test_build_xlsx_source_hyperlink(tmp_path, sample_json):
    data = build.load_data(sample_json)
    out = tmp_path / "out.xlsx"
    build.build_xlsx(data, out)
    wb = load_workbook(out)
    ws = wb["会議ログ"]
    url_cell = ws.cell(row=2, column=len(build.MEETING_HEADERS))
    assert url_cell.hyperlink is not None
    assert url_cell.hyperlink.target == "https://example.com/a"


def _write_macro_fixture(tmp_path):
    (tmp_path / "macro_data").mkdir()
    (tmp_path / "macro_data" / "M2SL.csv").write_text(
        "date,value,yoy_pct\n2019-01-01,100.0,\n2020-01-01,110.0,10.0\n", encoding="utf-8")
    (tmp_path / "series_config.json").write_text(
        json.dumps({"history_start": "2000-01-01", "history_points": 180,
                    "series": [{"id": "M2SL", "country": "米国",
                                "indicator": "マネーサプライ(M2)", "unit": "10億ドル",
                                "transform": "yoy_pct_also"}]}), encoding="utf-8")


def test_build_macro_payload(tmp_path):
    _write_macro_fixture(tmp_path)
    payload = build.build_macro_payload(
        config_path=tmp_path / "series_config.json", data_dir=tmp_path / "macro_data")
    s = payload["series"][0]
    assert s["country"] == "米国"
    assert s["latest"] == 110.0
    assert s["latest_date"] == "2020-01-01"
    assert s["yoy"] == 10.0
    assert s["history"] == [["2019-01-01", 100.0], ["2020-01-01", 110.0]]
    assert s["history_yoy"] == [["2020-01-01", 10.0]]


def test_macro_timeseries_rows(tmp_path):
    _write_macro_fixture(tmp_path)
    rows = build.macro_timeseries_rows(
        config_path=tmp_path / "series_config.json", data_dir=tmp_path / "macro_data")
    assert ("2020-01-01", "米国", "マネーサプライ(M2)", 110.0, 10.0) in rows


def test_build_xlsx_includes_macro_sheets(tmp_path, sample_json, monkeypatch):
    _write_macro_fixture(tmp_path)
    monkeypatch.setattr(build, "SERIES_CONFIG", tmp_path / "series_config.json")
    monkeypatch.setattr(build, "MACRO_DIR", tmp_path / "macro_data")
    data = build.load_data(sample_json)
    data["macro"] = build.build_macro_payload(
        config_path=tmp_path / "series_config.json", data_dir=tmp_path / "macro_data")
    out = tmp_path / "out.xlsx"
    build.build_xlsx(data, out)
    wb = load_workbook(out)
    assert "マクロ_最新" in wb.sheetnames
    assert "マクロ_時系列" in wb.sheetnames
    assert wb["マクロ_最新"].cell(row=1, column=1).value == "国"
    assert wb["マクロ_最新"].max_row == 2          # ヘッダ + 1シリーズ
    assert wb["マクロ_時系列"].max_row == 3         # ヘッダ + 2行


def test_build_macro_payload_includes_group(tmp_path):
    _write_macro_fixture(tmp_path)
    p = build.build_macro_payload(
        config_path=tmp_path / "series_config.json", data_dir=tmp_path / "macro_data")
    assert p["series"][0]["group"] == "fundamental"
