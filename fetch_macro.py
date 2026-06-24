#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FRED からマクロ時系列を取得し macro_data/*.csv を生成する。"""
import csv
import io
import json
import re
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
ECB_URL = "https://data-api.ecb.europa.eu/service/data"
BOJ_M2_CSV = "https://www.stat-search.boj.or.jp/ssi/mtshtml/csv/md02_m_1.csv"
BOJ_M2_CODE = "MD02'MAM1NAM2M2MO"   # マネーストック M2 平均残高(億円)
CFTC_URL = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"


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


def _parse_ecb_csv(text: str) -> list:
    rows = []
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        tp = (row.get("TIME_PERIOD") or "").strip()
        ov = (row.get("OBS_VALUE") or "").strip()
        if not tp or ov == "":
            continue
        try:
            v = float(ov)
        except ValueError:
            continue
        if len(tp) == 7:        # YYYY-MM
            d = tp + "-01"
        elif len(tp) == 4:      # YYYY
            d = tp + "-01-01"
        else:                   # YYYY-MM-DD など
            d = tp
        rows.append((d, v))
    rows.sort(key=lambda r: r[0])
    return rows


def fetch_ecb_series(ecb_key: str, urlopen=urllib.request.urlopen) -> list:
    url = f"{ECB_URL}/{ecb_key}?format=csvdata"
    req = urllib.request.Request(url, headers={"Accept": "text/csv"})
    with urlopen(req, timeout=30) as r:
        text = r.read().decode("utf-8")
    return _parse_ecb_csv(text)


def _parse_boj_m2_csv(text: str) -> list:
    reader = list(csv.reader(io.StringIO(text)))
    code_row = next((r for r in reader if r and r[0] == "データコード"), None)
    if not code_row or BOJ_M2_CODE not in code_row:
        return []
    col = code_row.index(BOJ_M2_CODE)
    out = []
    for r in reader:
        if not r or not re.match(r"^\d{4}/\d{1,2}$", r[0]):
            continue
        if col >= len(r):
            continue
        val = r[col].strip().replace(",", "")
        if val in ("", "-", "ND", "NA"):
            continue
        try:
            v = float(val)
        except ValueError:
            continue
        y, m = r[0].split("/")
        out.append((f"{y}-{int(m):02d}-01", v / 10000.0))   # 億円→兆円
    out.sort(key=lambda x: x[0])
    return out


def fetch_boj_m2(url: str = BOJ_M2_CSV, urlopen=urllib.request.urlopen) -> list:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=30) as r:
        raw = r.read()
    return _parse_boj_m2_csv(raw.decode("cp932"))


def _parse_cftc_rows(records: list) -> list:
    out = []
    for r in records:
        d = (r.get("report_date_as_yyyy_mm_dd") or "")[:10]
        if not d:
            continue
        try:
            net = float(r.get("noncomm_positions_long_all")) - float(r.get("noncomm_positions_short_all"))
        except (TypeError, ValueError):
            continue
        out.append((d, net))
    out.sort(key=lambda x: x[0])
    return out


def fetch_cftc(market_name: str, urlopen=urllib.request.urlopen) -> list:
    params = {
        "$select": "report_date_as_yyyy_mm_dd,noncomm_positions_long_all,noncomm_positions_short_all",
        "$where": f"market_and_exchange_names='{market_name}'",
        "$order": "report_date_as_yyyy_mm_dd ASC",
        "$limit": "20000",
    }
    url = CFTC_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urlopen(req, timeout=60) as r:
        records = json.loads(r.read().decode("utf-8"))
    return _parse_cftc_rows(records)


def _nearest_prior(pairs: list, target: str):
    val = None
    for d, v in pairs:
        if d <= target:
            val = v
        else:
            break
    return val


def compute_netliq(walcl: list, tga: list, rrp: list) -> list:
    tga_s = sorted(tga)
    rrp_s = sorted(rrp)
    out = []
    for d, w in sorted(walcl):
        t = _nearest_prior(tga_s, d)
        r = _nearest_prior(rrp_s, d)
        if t is None or r is None:
            continue
        net = (w - t - r * 1000.0) / 1e6   # 百万ドル基準 → 兆ドル
        out.append((d, round(net, 4)))
    return out


def fetch_netliq(api_key, fred_fetcher=fetch_series) -> list:
    walcl = parse_observations(fred_fetcher("WALCL", api_key))
    tga = parse_observations(fred_fetcher("WTREGEN", api_key))
    rrp = parse_observations(fred_fetcher("RRPONTSYD", api_key))
    return compute_netliq(walcl, tga, rrp)


def computed_dispatch(series: dict, api_key: str, fred_fetcher=fetch_series) -> list:
    if series.get("compute") == "netliq_us":
        return fetch_netliq(api_key, fred_fetcher)
    raise ValueError(f"unknown compute: {series.get('compute')}")


def get_rows(series: dict, api_key: str, *, fred_fetcher, ecb_fetcher, boj_fetcher=None, computed_fetcher=None) -> list:
    src = series.get("source")
    if src == "ecb":
        return ecb_fetcher(series["ecb_key"])
    if src == "boj":
        return boj_fetcher()
    if src == "computed":
        return (computed_fetcher or computed_dispatch)(series, api_key, fred_fetcher)
    return parse_observations(fred_fetcher(series["id"], api_key))


def run(config: dict, api_key: str, fetcher=fetch_series, ecb_fetcher=None, boj_fetcher=None, computed_fetcher=None, data_dir: Path = MACRO_DIR) -> dict:
    if ecb_fetcher is None:
        ecb_fetcher = fetch_ecb_series
    if boj_fetcher is None:
        boj_fetcher = fetch_boj_m2
    ok, failed, skipped = [], [], []
    for s in config.get("series", []):
        sid = s["id"]
        if s.get("source") == "manual":
            skipped.append(sid)            # 手動採録: 取得も上書きもしない
            continue
        with_yoy = s.get("transform") == "yoy_pct_also"
        try:
            rows = get_rows(s, api_key, fred_fetcher=fetcher, ecb_fetcher=ecb_fetcher, boj_fetcher=boj_fetcher, computed_fetcher=computed_fetcher)
            if not rows:
                failed.append((sid, "観測値なし"))
                continue
            out = compute_yoy(rows) if with_yoy else rows
            write_series_csv(sid, out, with_yoy, data_dir)
            ok.append(sid)
        except Exception as e:  # noqa: BLE001  個別失敗はスキップして継続
            failed.append((sid, str(e)))
    return {"ok": ok, "failed": failed, "skipped": skipped}


def main() -> int:
    config = load_config()
    api_key = load_api_key()
    res = run(config, api_key)
    print(f"OK: {len(res['ok'])} series 取得")
    if res.get("skipped"):
        print(f"  手動(スキップ): {', '.join(res['skipped'])}")
    for sid, err in res["failed"]:
        print(f"  未取得 {sid}: {err}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
