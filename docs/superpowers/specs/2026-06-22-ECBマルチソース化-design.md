# ECBマルチソース化（ユーロ圏マネーサプライ追加）設計書

- 作成日: 2026-06-22
- 対象: 既存「G7一次情報＋マクロ数値ダッシュボード」への拡張
- 配置: `C:\Users\yutao\OneDrive\デスクトップ\★Claud code★\銀行一次情報`

## 1. 目的・背景

FREDの国際マネーサプライ系列は提供終了で、現状マクロの「マネーサプライ(M2)」は**米国のみ**。世界のマネーの流れを掴むため、**ユーロ圏のM2・M3をECB公式API**（無料・キー不要）から現行値で取得し追加する。

- 検証済み: ECB Data Portal `data-api.ecb.europa.eu` でユーロ圏M2が **2026-04（現行）** を返すことを実証。
- 日本M2は今回スコープ外（DBnomicsのBOJはマネーストック未収録、IMF経由は約16か月遅延のため、次回に日銀直CSVで対応）。

## 2. スコープ（確定要件）

| 項目 | 決定 |
|---|---|
| 追加データ | ユーロ圏 **M2** と **M3**（ECB公式API） |
| ラベル | M2→`マネーサプライ(M2)`（米国と同カテゴリで比較）、M3→`マネーサプライ(M3)`（独立カテゴリ） |
| 日本M2 | 今回スコープ外（次回・日銀直CSV） |
| 既存への影響 | build.py・Excel・ダッシュボードの大半は無変更で自動反映。1点だけ index.html を微調整 |

### スコープ外（YAGNI）
- 日本/英国/中国のマネーサプライ、BOJ/BoE/PBOC連携、ECBの他系列の網羅。

## 3. アーキテクチャ：fetch_macro のマルチソース化

`series_config.json` の各系列に `source`（`fred`＝既定／`ecb`）を持たせ、取得時にソース別fetcherへ振り分ける。**各ソースは結果を共通の行形式 `[(YYYY-MM-01, float)]` に正規化して返す**ため、以降のYoY計算・CSV書き出し・ビルド・表示はソース非依存で流用できる。

```
series_config.json (source: fred|ecb)
        │
   run() ─ get_rows(series) ─ source分岐
        ├─ fred: parse_observations(fetch_series(id, key))
        └─ ecb : fetch_ecb_series(ecb_key)   ← CSV取得＋日付正規化
        │
   compute_yoy → write_series_csv（既存）
        │
   build.py / index.html（既存・ほぼ無変更）
```

## 4. データソース（ECB）

- エンドポイント: `https://data-api.ecb.europa.eu/service/data/{ecb_key}?format=csvdata`（`Accept: text/csv`、無料・キー不要）
- `ecb_key` 例: `BSI/M.U2.Y.V.M20.X.1.U2.2300.Z01.E`（M2）、`BSI/M.U2.Y.V.M30.X.1.U2.2300.Z01.E`（M3）
- CSV列: 多数あるが使うのは **`TIME_PERIOD`**（例 `2026-04`）と **`OBS_VALUE`**。引用符内にカンマを含む列があるため**csvモジュールで解析**（naive splitは不可）。
- 日付正規化: `2026-04` → `2026-04-01`（FREDの月次形式に揃える）。

## 5. 設定追加（series_config.json）

既存FRED系列は `source` 省略（=fred）。新規にECB 2系列を追加:

```jsonc
{ "id": "ECB_M2_EUR", "country": "ユーロ圏", "indicator": "マネーサプライ(M2)",
  "unit": "百万ユーロ", "transform": "yoy_pct_also",
  "source": "ecb", "ecb_key": "BSI/M.U2.Y.V.M20.X.1.U2.2300.Z01.E" },
{ "id": "ECB_M3_EUR", "country": "ユーロ圏", "indicator": "マネーサプライ(M3)",
  "unit": "百万ユーロ", "transform": "yoy_pct_also",
  "source": "ecb", "ecb_key": "BSI/M.U2.Y.V.M30.X.1.U2.2300.Z01.E" }
```

CSVファイル名は `id`（`ECB_M2_EUR.csv` 等）。

## 6. fetch_macro.py の変更

- `fetch_ecb_series(ecb_key, urlopen=...) -> list[tuple[str,float]]`:
  ECBをCSV取得 → `csv.DictReader` で `TIME_PERIOD/OBS_VALUE` を読み、欠損を除外、日付を `YYYY-MM-01` に正規化、日付昇順で返す。
- `get_rows(series, api_key, *, fred_fetcher, ecb_fetcher) -> list[tuple[str,float]]`:
  `series.get("source","fred")` で分岐。`ecb`→`ecb_fetcher(series["ecb_key"])`、既定→`parse_observations(fred_fetcher(series["id"], api_key))`。
- `run()` を `get_rows` 経由に変更（FRED専用呼び出しを置換）。`transform=="yoy_pct_also"` のときYoY付与、`write_series_csv` する流れは不変。
- ネットワーク/解析失敗はそのシリーズをスキップしログ（既存方針）。

## 7. ダッシュボードの小調整（index.html）

`renderMoneyFlow` のM2比較フィルタを **`s.indicator === "マネーサプライ(M2)"`（完全一致）** に変更。これにより M2比較チャートは **米国M2＋ユーロ圏M2** のみとなり、M3（ユーロ圏）は「マクロ」ビューの独立カテゴリcardとして表示（比較チャートには混ざらない）。

## 8. 影響範囲（変更しないもの）
- `build.py`・Excel生成・`macro_timeseries_rows`・大半のindex.html は**無変更**（設定に新系列が増えるだけで自動的にカード/シート/時系列へ反映）。
- 自動更新（`update_macro.bat` / タスクスケジューラ）も**無変更**で次回からユーロM2/M3を取得。

## 9. エラーハンドリング
- ECB取得失敗（HTTP/解析）はそのシリーズをスキップし標準エラーに明示。FRED分は影響を受けない。
- 値が空/非数値の行は除外。出典のない値は入れない。

## 10. テスト
- `fetch_ecb_series`: サンプルECB CSV（引用符内カンマ・`2026-04`形式・欠損行を含む）を入力に、`[("2026-04-01", 16289850.0), ...]` を日付昇順で返すことを検証（`urlopen`をモック）。
- `get_rows`: `source:"ecb"` でECB fetcherが、既定でFRED fetcherが呼ばれることを検証（fetcher注入）。
- 既存テストを壊さない（`python -m pytest` 全PASS）。

## 11. 受け入れ基準
- [ ] `python fetch_macro.py` でユーロ圏M2・M3が `macro_data/ECB_M2_EUR.csv` `ECB_M3_EUR.csv` に現行値で保存される。
- [ ] 「マクロ」ビューで「マネーサプライ(M2)」に米国＋ユーロ圏、「マネーサプライ(M3)」にユーロ圏が表示される。
- [ ] 「マネーの流れ」のM2比較に米国＋ユーロ圏が並ぶ。
- [ ] Excel `マクロ_最新`/`マクロ_時系列` にユーロ圏M2/M3が反映される。
- [ ] `python -m pytest` 全PASS（既存を壊さない）。
- [ ] ECB取得は無料・APIキー不要で動作する。
