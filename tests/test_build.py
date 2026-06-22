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
    assert wb.sheetnames == ["会議ログ", "カレンダー", "考察サマリ"]
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
