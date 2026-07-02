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


def test_load_api_key_missing_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        fetch_macro.load_api_key(tmp_path / "nope.txt")


def test_load_api_key_prefers_env(tmp_path, monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "envkey123")
    # ファイルが無くても環境変数を使う（CI向け）
    assert fetch_macro.load_api_key(tmp_path / "nope.txt") == "envkey123"


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


def test_run_writes_ok_and_skips_failures(tmp_path):
    cfg = {"series": [
        {"id": "GOOD", "transform": "yoy_pct_also"},
        {"id": "BAD", "transform": "level"},
        {"id": "EMPTY", "transform": "level"},
    ]}

    def fake_fetcher(sid, key):
        if sid == "GOOD":
            return {"observations": [
                {"date": "2020-01-01", "value": "100"},
                {"date": "2021-01-01", "value": "110"},
            ]}
        if sid == "EMPTY":
            return {"observations": []}
        raise RuntimeError("boom")

    res = fetch_macro.run(cfg, "key", fetcher=fake_fetcher, data_dir=tmp_path)
    assert res["ok"] == ["GOOD"]
    failed_ids = [f[0] for f in res["failed"]]
    assert "BAD" in failed_ids and "EMPTY" in failed_ids
    good = (tmp_path / "GOOD.csv").read_text(encoding="utf-8")
    assert good.startswith("date,value,yoy_pct")
    assert "10.0" in good  # YoY が計算されている


class _FakeResp:
    def __init__(self, text): self._t = text
    def read(self): return self._t.encode("utf-8")
    def __enter__(self): return self
    def __exit__(self, *a): return False


def test_parse_ecb_csv_normalizes_and_handles_quoted_commas():
    text = ('TIME_PERIOD,OBS_VALUE,TITLE_COMPL\n'
            '2026-03,16282398,"M2, stocks"\n'
            '2026-02,16244868,"M2, stocks"\n'
            '2026-04,,"empty value"\n')
    rows = fetch_macro._parse_ecb_csv(text)
    assert rows == [("2026-02-01", 16244868.0), ("2026-03-01", 16282398.0)]


def test_fetch_ecb_series_builds_url_and_parses():
    captured = {}
    def fake_urlopen(req, timeout=30):
        captured["url"] = req.full_url
        return _FakeResp("TIME_PERIOD,OBS_VALUE\n2026-03,16282398\n2026-02,16244868\n")
    rows = fetch_macro.fetch_ecb_series("BSI/M.U2.Y.V.M20.X.1.U2.2300.Z01.E", urlopen=fake_urlopen)
    assert "data-api.ecb.europa.eu/service/data/BSI/M.U2.Y.V.M20.X.1.U2.2300.Z01.E" in captured["url"]
    assert "format=csvdata" in captured["url"]
    assert rows == [("2026-02-01", 16244868.0), ("2026-03-01", 16282398.0)]


def test_get_rows_dispatches_by_source():
    fred_calls, ecb_calls = [], []
    def fake_fred(sid, key):
        fred_calls.append(sid)
        return {"observations": [{"date": "2020-01-01", "value": "1"}]}
    def fake_ecb(key):
        ecb_calls.append(key)
        return [("2026-04-01", 16289850.0)]
    r_fred = fetch_macro.get_rows({"id": "M2SL"}, "key",
                                  fred_fetcher=fake_fred, ecb_fetcher=fake_ecb)
    r_ecb = fetch_macro.get_rows({"id": "X", "source": "ecb", "ecb_key": "BSI/KEY"}, "key",
                                 fred_fetcher=fake_fred, ecb_fetcher=fake_ecb)
    assert fred_calls == ["M2SL"] and r_fred == [("2020-01-01", 1.0)]
    assert ecb_calls == ["BSI/KEY"] and r_ecb == [("2026-04-01", 16289850.0)]


def test_run_handles_ecb_source(tmp_path):
    cfg = {"series": [{"id": "ECB_M2_EUR", "source": "ecb",
                       "ecb_key": "BSI/KEY", "transform": "yoy_pct_also"}]}
    def fake_ecb(key):
        return [("2025-04-01", 100.0), ("2026-04-01", 110.0)]
    res = fetch_macro.run(cfg, "key", ecb_fetcher=fake_ecb, data_dir=tmp_path)
    assert res["ok"] == ["ECB_M2_EUR"]
    txt = (tmp_path / "ECB_M2_EUR.csv").read_text(encoding="utf-8")
    assert txt.startswith("date,value,yoy_pct")
    assert "10.0" in txt  # YoY +10%


def test_run_skips_manual_source(tmp_path):
    existing = "date,value,yoy_pct\n2026-04-01,1259.0,1.5\n"
    (tmp_path / "JP_M2_MANUAL.csv").write_text(existing, encoding="utf-8")
    cfg = {"series": [{"id": "JP_M2_MANUAL", "source": "manual", "transform": "yoy_pct_also"}]}
    def boom_fred(sid, key): raise AssertionError("manualはfetchしないはず")
    def boom_ecb(key): raise AssertionError("manualはfetchしないはず")
    res = fetch_macro.run(cfg, "key", fetcher=boom_fred, ecb_fetcher=boom_ecb, data_dir=tmp_path)
    assert res["skipped"] == ["JP_M2_MANUAL"]
    assert res["ok"] == [] and res["failed"] == []
    # 既存の手動CSVが上書きされていない
    assert (tmp_path / "JP_M2_MANUAL.csv").read_text(encoding="utf-8") == existing


def test_parse_boj_m2_csv_extracts_m2_level_in_chocho():
    text = (
        "主要時系列統計データ表\n"
        "2026/06/23 15:00\n"
        ",M2前年比,M2平残\n"
        "系列名称,M2/前年比,M2/平残\n"
        "データコード,MD02'MAM1YAM2M2MO,MD02'MAM1NAM2M2MO\n"
        "単位,%,億円\n"
        "2025/05,2.4,12660000\n"
        "2026/05,2.5,12980932\n"
    )
    rows = fetch_macro._parse_boj_m2_csv(text)
    assert rows == [("2025-05-01", 1266.0), ("2026-05-01", 1298.0932)]


def test_fetch_boj_m2_decodes_cp932():
    sample = (
        "x\nx\nx\n系列名称,M2/平残\nデータコード,MD02'MAM1NAM2M2MO\n単位,億円\n"
        "2026/05,12980932\n"
    )
    class _R:
        def __init__(self, b): self._b = b
        def read(self): return self._b
        def __enter__(self): return self
        def __exit__(self, *a): return False
    def fake_urlopen(req, timeout=30):
        return _R(sample.encode("cp932"))
    rows = fetch_macro.fetch_boj_m2(urlopen=fake_urlopen)
    assert rows == [("2026-05-01", 1298.0932)]


def test_run_handles_boj_source(tmp_path):
    cfg = {"series": [{"id": "JP_M2_BOJ", "source": "boj", "transform": "yoy_pct_also"}]}
    def fake_boj():
        return [("2025-05-01", 1266.0), ("2026-05-01", 1298.0932)]
    res = fetch_macro.run(cfg, "key", boj_fetcher=fake_boj, data_dir=tmp_path)
    assert res["ok"] == ["JP_M2_BOJ"]
    txt = (tmp_path / "JP_M2_BOJ.csv").read_text(encoding="utf-8")
    assert txt.startswith("date,value,yoy_pct")
    assert "2026-05-01" in txt


def test_nearest_prior():
    pairs = [("2026-06-10", 1.0), ("2026-06-17", 2.0), ("2026-06-22", 3.0)]
    assert fetch_macro._nearest_prior(pairs, "2026-06-18") == 2.0
    assert fetch_macro._nearest_prior(pairs, "2026-06-22") == 3.0
    assert fetch_macro._nearest_prior(pairs, "2026-06-09") is None


def test_compute_netliq_units_and_alignment():
    walcl = [("2026-06-10", 6700000.0), ("2026-06-17", 6736424.0)]   # 百万ドル
    tga   = [("2026-06-10", 870000.0), ("2026-06-17", 880713.0)]     # 百万ドル
    rrp   = [("2026-06-15", 5.0), ("2026-06-17", 3.925)]             # 十億ドル
    out = fetch_macro.compute_netliq(walcl, tga, rrp)
    # 2026-06-10 は rrp の直近以前値が無く除外。2026-06-17 のみ。
    # (6736424 - 880713 - 3.925*1000)/1e6 = 5.851786 → 5.8518
    assert out == [("2026-06-17", 5.8518)]


def test_fetch_netliq_uses_three_fred_series():
    def fred(sid, key):
        data = {
            "WALCL": [{"date": "2026-06-17", "value": "6736424"}],
            "WTREGEN": [{"date": "2026-06-17", "value": "880713"}],
            "RRPONTSYD": [{"date": "2026-06-17", "value": "3.925"}],
        }[sid]
        return {"observations": data}
    rows = fetch_macro.fetch_netliq("key", fred_fetcher=fred)
    assert rows == [("2026-06-17", 5.8518)]


def test_run_handles_computed_source(tmp_path):
    cfg = {"series": [{"id": "NETLIQ_US", "source": "computed",
                       "compute": "netliq_us", "transform": "yoy_pct_also"}]}
    def fake_computed(series, api_key, fred_fetcher):
        return [("2025-06-17", 5.0), ("2026-06-17", 5.85)]
    res = fetch_macro.run(cfg, "key", computed_fetcher=fake_computed, data_dir=tmp_path)
    assert res["ok"] == ["NETLIQ_US"]
    txt = (tmp_path / "NETLIQ_US.csv").read_text(encoding="utf-8")
    assert txt.startswith("date,value,yoy_pct")
    assert "2026-06-17" in txt


def test_parse_cftc_rows_net_and_sort():
    recs = [
        {"report_date_as_yyyy_mm_dd": "2026-06-16T00:00:00.000",
         "noncomm_positions_long_all": "250000", "noncomm_positions_short_all": "69780"},
        {"report_date_as_yyyy_mm_dd": "2026-06-09T00:00:00.000",
         "noncomm_positions_long_all": "240000", "noncomm_positions_short_all": "60000"},
    ]
    out = fetch_macro._parse_cftc_rows(recs)
    assert out == [("2026-06-09", 180000.0), ("2026-06-16", 180220.0)]


def test_fetch_cftc_builds_query_and_parses():
    import urllib.parse
    captured = {}
    body = ('[{"report_date_as_yyyy_mm_dd":"2026-06-16T00:00:00.000",'
            '"noncomm_positions_long_all":"250000","noncomm_positions_short_all":"69780"}]')
    class _R:
        def read(self): return body.encode("utf-8")
        def __enter__(self): return self
        def __exit__(self, *a): return False
    def fake_urlopen(req, timeout=60):
        captured["url"] = req.full_url
        return _R()
    rows = fetch_macro.fetch_cftc("GOLD - COMMODITY EXCHANGE INC.", urlopen=fake_urlopen)
    assert "publicreporting.cftc.gov" in captured["url"]
    assert "GOLD" in urllib.parse.unquote(captured["url"])
    assert rows == [("2026-06-16", 180220.0)]


def test_deflate_real():
    nominal = [("2026-03-01", 21000.0), ("2026-04-01", 22000.0)]
    cpi = [("2026-03-01", 310.0), ("2026-04-01", 320.0)]
    out = fetch_macro._deflate(nominal, cpi)
    assert out[-1] == ("2026-04-01", 6875.0)   # 22000/(320/100)


def test_fetch_real_m2_uses_m2_and_cpi():
    def fred(sid, key):
        data = {"M2SL": [{"date": "2026-04-01", "value": "22000"}],
                "CPIAUCSL": [{"date": "2026-04-01", "value": "320"}]}[sid]
        return {"observations": data}
    rows = fetch_macro.fetch_real_m2("key", fred_fetcher=fred)
    assert rows == [("2026-04-01", 6875.0)]


def test_fetch_global_liq_converts_and_aligns():
    def fred(sid, key):
        data = {
            "WALCL": [{"date": "2026-06-17", "value": "6700000"},
                       {"date": "2026-06-24", "value": "6735645"}],
            "ECBASSETSW": [{"date": "2026-06-19", "value": "6119940"}],
            "JPNASSETS": [{"date": "2026-05-01", "value": "6643630"}],
            "DEXUSEU": [{"date": "2026-06-18", "value": "1.147"}],
            "DEXJPUS": [{"date": "2026-06-18", "value": "161.37"}],
        }[sid]
        return {"observations": data}
    rows = fetch_macro.fetch_global_liq("key", fred_fetcher=fred)
    # 2026-06-17 は ECB/EURUSD/USDJPY の直近以前値が無く除外。06-24 のみ。
    assert len(rows) == 1
    d, v = rows[0]
    assert d == "2026-06-24"
    assert abs(v - 17.8722) < 0.001   # 検算値


def test_computed_dispatch_global_liq():
    import fetch_macro as fm
    called = {}
    def fake(k, fred_fetcher=None):
        called["ok"] = True
        return [("2026-06-24", 17.87)]
    orig = fm.fetch_global_liq
    fm.fetch_global_liq = fake
    try:
        out = fm.computed_dispatch({"compute": "global_liq"}, "key")
        assert called.get("ok") and out == [("2026-06-24", 17.87)]
    finally:
        fm.fetch_global_liq = orig


def test_fetch_spread_aligns_and_subtracts():
    def fred(sid, key):
        data = {
            "DGS10": [{"date": "2026-06-17", "value": "4.5"},
                      {"date": "2026-06-18", "value": "4.46"}],
            "IRLTLT01JPM156N": [{"date": "2026-05-01", "value": "2.65"}],
        }[sid]
        return {"observations": data}
    rows = fetch_macro.fetch_spread("DGS10", "IRLTLT01JPM156N", "key", fred_fetcher=fred)
    assert rows == [("2026-06-17", 1.85), ("2026-06-18", 1.81)]


def test_computed_dispatch_spread():
    def fred(sid, key):
        data = {"A": [{"date": "2026-06-18", "value": "4.0"}],
                "B": [{"date": "2026-06-18", "value": "2.5"}]}[sid]
        return {"observations": data}
    out = fetch_macro.computed_dispatch(
        {"compute": "spread", "minuend": "A", "subtrahend": "B"}, "key", fred_fetcher=fred)
    assert out == [("2026-06-18", 1.5)]


def test_run_handles_cftc_source(tmp_path):
    cfg = {"series": [{"id": "COT_GOLD", "source": "cftc",
                       "cftc_market": "GOLD - X", "transform": "level"}]}
    def fake_cftc(market):
        return [("2026-06-09", 180000.0), ("2026-06-16", 180220.0)]
    res = fetch_macro.run(cfg, "key", cftc_fetcher=fake_cftc, data_dir=tmp_path)
    assert res["ok"] == ["COT_GOLD"]
    txt = (tmp_path / "COT_GOLD.csv").read_text(encoding="utf-8")
    assert "180220" in txt
