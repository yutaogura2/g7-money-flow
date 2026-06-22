#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""data.json から data.js（ブラウザ用）と Excel を生成する。"""
import json
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent
DATA_JSON = ROOT / "data.json"
DATA_JS = ROOT / "data.js"
XLSX = ROOT / "G7_一次情報ログ.xlsx"


def load_data(path: Path = DATA_JSON) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_data_js(data: dict, path: Path = DATA_JS) -> None:
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    Path(path).write_text(f"window.G7DATA = {payload};\n", encoding="utf-8")


MEETING_HEADERS = [
    "日付", "種別", "議長国", "邦題", "原題", "要約", "決定事項",
    "主要部分の全訳", "考察(為替・金利)", "考察(商品・エネルギー・金)",
    "考察(セクター)", "考察(地政学)", "方向性メモ", "タグ", "原文URL",
]
CALENDAR_HEADERS = ["日付", "名称", "カテゴリ", "状態", "関連会議ID", "備考"]
ANALYSIS_HEADERS = ["日付", "観点", "論点", "関連会議ID"]

ASPECTS = [
    ("fx_rates", "為替・金利"),
    ("commodities", "商品・エネルギー・金"),
    ("sectors", "セクター"),
    ("geopolitics", "地政学"),
]


def _style_header(ws) -> None:
    fill = PatternFill("solid", fgColor="1F3864")
    font = Font(bold=True, color="FFFFFF")
    for cell in ws[1]:
        cell.fill = fill
        cell.font = font
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions


def build_xlsx(data: dict, path: Path = XLSX) -> None:
    wb = Workbook()

    ws1 = wb.active
    ws1.title = "会議ログ"
    ws1.append(MEETING_HEADERS)
    for m in data.get("meetings", []):
        a = m.get("analysis", {})
        ws1.append([
            m.get("date", ""), m.get("type", ""), m.get("presidency", ""),
            m.get("title_ja", ""), m.get("title_orig", ""), m.get("summary_ja", ""),
            "\n".join(m.get("key_points_ja", [])), m.get("full_translation_ja", ""),
            a.get("fx_rates", ""), a.get("commodities", ""),
            a.get("sectors", ""), a.get("geopolitics", ""),
            m.get("market_direction", ""), ", ".join(m.get("tags", [])),
            m.get("source_url", ""),
        ])
        url = m.get("source_url", "")
        if url:
            c = ws1.cell(row=ws1.max_row, column=len(MEETING_HEADERS))
            c.hyperlink = url
            c.font = Font(color="0563C1", underline="single")
    _style_header(ws1)

    ws2 = wb.create_sheet("カレンダー")
    ws2.append(CALENDAR_HEADERS)
    for e in sorted(data.get("calendar", []), key=lambda x: x.get("date", "")):
        ws2.append([
            e.get("date", ""), e.get("name_ja", ""), e.get("category", ""),
            e.get("status", ""), e.get("related_meeting_id") or "", e.get("note", ""),
        ])
    _style_header(ws2)

    ws3 = wb.create_sheet("考察サマリ")
    ws3.append(ANALYSIS_HEADERS)
    for m in data.get("meetings", []):
        a = m.get("analysis", {})
        for key, label in ASPECTS:
            text = a.get(key, "")
            if text:
                ws3.append([m.get("date", ""), label, text, m.get("id", "")])
    _style_header(ws3)

    for ws in wb.worksheets:
        for col in range(1, ws.max_column + 1):
            ws.column_dimensions[get_column_letter(col)].width = 24

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def main() -> int:
    data = load_data()
    write_data_js(data)
    build_xlsx(data)
    print(f"OK: {len(data.get('meetings', []))} meetings, "
          f"{len(data.get('calendar', []))} calendar events")
    return 0


if __name__ == "__main__":
    sys.exit(main())
