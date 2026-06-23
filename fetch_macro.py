#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FRED からマクロ時系列を取得し macro_data/*.csv を生成する。"""
import json
import sys
import urllib.parse
import urllib.request
from datetime import date
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


def parse_observations(payload: dict) -> list:
    out = []
    for o in payload.get("observations", []):
        val = o.get("value", ".")
        if val in (".", "", None):
            continue
        try:
            out.append((o["date"], float(val)))
        except (ValueError, KeyError):
            continue
    out.sort(key=lambda r: r[0])
    return out


def _prev_year(d: str) -> str:
    y, m, dd = (int(x) for x in d.split("-"))
    try:
        return date(y - 1, m, dd).isoformat()
    except ValueError:        # 2月29日など
        return date(y - 1, m, 28).isoformat()


def compute_yoy(rows: list) -> list:
    out = []
    for i, (d, v) in enumerate(rows):
        target = _prev_year(d)
        prev = None
        for dj, vj in rows[:i]:
            if dj <= target:
                prev = vj
            else:
                break
        yoy = round((v / prev - 1) * 100, 2) if prev not in (None, 0) else None
        out.append((d, v, yoy))
    return out


def to_csv_text(rows: list, with_yoy: bool) -> str:
    if with_yoy:
        lines = ["date,value,yoy_pct"]
        for d, v, y in rows:
            lines.append(f"{d},{v},{'' if y is None else y}")
    else:
        lines = ["date,value"]
        for d, v in rows:
            lines.append(f"{d},{v}")
    return "\n".join(lines) + "\n"


def write_series_csv(series_id: str, rows: list, with_yoy: bool, data_dir: Path = MACRO_DIR) -> Path:
    p = Path(data_dir)
    p.mkdir(parents=True, exist_ok=True)
    fp = p / f"{series_id}.csv"
    fp.write_text(to_csv_text(rows, with_yoy), encoding="utf-8")
    return fp


def fetch_series(series_id: str, api_key: str, urlopen=urllib.request.urlopen) -> dict:
    q = urllib.parse.urlencode({"series_id": series_id, "api_key": api_key, "file_type": "json"})
    with urlopen(f"{FRED_URL}?{q}", timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def run(config: dict, api_key: str, fetcher=fetch_series, data_dir: Path = MACRO_DIR) -> dict:
    ok, failed = [], []
    for s in config.get("series", []):
        sid = s["id"]
        with_yoy = s.get("transform") == "yoy_pct_also"
        try:
            rows = parse_observations(fetcher(sid, api_key))
            if not rows:
                failed.append((sid, "観測値なし"))
                continue
            out = compute_yoy(rows) if with_yoy else rows
            write_series_csv(sid, out, with_yoy, data_dir)
            ok.append(sid)
        except Exception as e:  # noqa: BLE001  個別失敗はスキップして継続
            failed.append((sid, str(e)))
    return {"ok": ok, "failed": failed}


def main() -> int:
    config = load_config()
    api_key = load_api_key()
    res = run(config, api_key)
    print(f"OK: {len(res['ok'])} series 取得")
    for sid, err in res["failed"]:
        print(f"  未取得 {sid}: {err}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
