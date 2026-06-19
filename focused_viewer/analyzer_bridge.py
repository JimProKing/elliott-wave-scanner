"""지정종목 엘리어트 분석 모듈 연결 (로컬 / 웹 / EXE 공용)."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

_APP_DIR = Path(__file__).resolve().parent
_DATA_DIR = _APP_DIR / "data"
_DATA_FILE = _DATA_DIR / "latest.json"

# vendor(배포용) → 바이낸스 폴더(로컬 개발) 순으로 탐색
_VENDOR_DIR = _APP_DIR / "vendor"
_BINANCE_DIR = _APP_DIR.parent.parent / "바이낸스"

if getattr(sys, "frozen", False):
    _MODULE_DIR = Path(sys._MEIPASS) / "바이낸스"
    _RESULTS_BASE = Path(sys.executable).resolve().parent.parent / "바이낸스"
elif _VENDOR_DIR.exists() and (_VENDOR_DIR / "엘리어트_지정종목_분석.py").exists():
    _MODULE_DIR = _VENDOR_DIR
    _RESULTS_BASE = _BINANCE_DIR if _BINANCE_DIR.exists() else _APP_DIR
elif _BINANCE_DIR.exists():
    _MODULE_DIR = _BINANCE_DIR
    _RESULTS_BASE = _BINANCE_DIR
else:
    _MODULE_DIR = Path(os.environ.get("BINANCE_DIR", "C:/Users/a/Documents/Trading/바이낸스"))
    _RESULTS_BASE = _MODULE_DIR

if str(_MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(_MODULE_DIR))

from 엘리어트_지정종목_분석 import (  # noqa: E402
    DEFAULT_TOP_N,
    fetch_klines,
    get_top_volume_coins,
    run_focused_analysis,
    save_reports,
)

RESULTS_DIR = (_RESULTS_BASE if _RESULTS_BASE.exists() else _MODULE_DIR) / "지정종목_엘리어트분석"


def _normalize_payload(data: Dict) -> Dict:
    if not data:
        return data
    if "results" not in data and "coins" in data:
        pass
    data.setdefault("interval", "4h")
    data.setdefault("lookback", 110)
    data.setdefault("top_n", DEFAULT_TOP_N)
    data.setdefault("pool", f"Binance USDT top {data.get('top_n', DEFAULT_TOP_N)} by 24h volume")
    return data


def save_to_data_file(payload: Dict) -> Path:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return _DATA_FILE


def run_analysis(interval: str = "4h", lookback: int = 110, top_n: int = DEFAULT_TOP_N, save: bool = True) -> Dict:
    results = run_focused_analysis(interval=interval, lookback=lookback, top_n=top_n)
    saved_path = None

    payload = {
        "generated_at": datetime.now().isoformat(),
        "interval": interval,
        "lookback": lookback,
        "top_n": top_n,
        "pool": f"Binance USDT top {top_n} by 24h volume",
        "coins": [r["symbol"] for r in results],
        "results": results,
    }

    if results:
        save_to_data_file(payload)
        if save and not os.environ.get("WEB_DEPLOY"):
            saved_path = str(save_reports(results, top_n=top_n))

    return {
        **payload,
        "saved_path": saved_path,
    }


def load_latest_saved() -> Optional[Dict]:
    if _DATA_FILE.exists():
        with open(_DATA_FILE, "r", encoding="utf-8") as f:
            data = _normalize_payload(json.load(f))
            data["source_file"] = "data/latest.json"
            return data

    if not RESULTS_DIR.exists():
        return None
    json_files = sorted(RESULTS_DIR.glob("*_지정종목_엘리어트_분석.json"), reverse=True)
    if not json_files:
        return None
    with open(json_files[0], "r", encoding="utf-8") as f:
        data = _normalize_payload(json.load(f))
        data["source_file"] = json_files[0].name
        return data


def list_saved_reports(limit: int = 10) -> List[Dict]:
    items = []
    if _DATA_FILE.exists():
        try:
            mtime = datetime.fromtimestamp(_DATA_FILE.stat().st_mtime)
            items.append({
                "filename": "data/latest.json",
                "generated_at": mtime.isoformat(),
                "is_live": True,
            })
        except Exception:
            pass

    if RESULTS_DIR.exists():
        for f in sorted(RESULTS_DIR.glob("*_지정종목_엘리어트_분석.json"), reverse=True)[:limit]:
            try:
                ts = f.stem.split("_")[0] + "_" + f.stem.split("_")[1]
                dt = datetime.strptime(ts, "%Y%m%d_%H%M")
                generated_at = dt.isoformat()
            except Exception:
                generated_at = None
            items.append({
                "filename": f.name,
                "generated_at": generated_at,
                "is_live": False,
            })
    return items[:limit]


def load_report(filename: str) -> Optional[Dict]:
    if filename in ("data/latest.json", "latest.json"):
        return load_latest_saved()
    path = RESULTS_DIR / filename
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return _normalize_payload(json.load(f))


def get_coin_candles(symbol: str, interval: str = "4h", limit: int = 110) -> List[Dict]:
    return fetch_klines(symbol, interval=interval, limit=limit)


def get_saved_chart_candles(coin: Dict, limit: int = 72) -> List[Dict]:
    """스캔 시 저장된 차트용 OHLC (1h 3일 우선)."""
    saved = (
        coin.get("chart_display_candles")
        or coin.get("chart_candles")
        or coin.get("candles")
        or []
    )
    if not saved:
        return []
    if limit and len(saved) > limit:
        return saved[-limit:]
    return saved


def get_chart_display_meta(coin: Dict, data: Optional[Dict] = None) -> tuple[str, int]:
    interval = coin.get("chart_display_interval") or (data or {}).get("chart_display_interval") or "1h"
    days = int(coin.get("chart_display_days") or (data or {}).get("chart_display_days") or 3)
    return interval, days


def resolve_chart_candles(
    coin: Dict,
    symbol: str,
    interval: str = "1h",
    limit: int = 72,
    *,
    allow_live_fetch: bool = True,
) -> tuple[List[Dict], Optional[str], str, int]:
    chart_interval, chart_days = get_chart_display_meta(coin)
    saved = get_saved_chart_candles(coin, limit=limit)
    min_needed = 8

    if len(saved) >= min_needed:
        return saved, None, chart_interval, chart_days

    # 구버전 4h 데이터: 최근 3일(18봉)만 사용
    legacy = coin.get("chart_candles") or []
    if len(legacy) >= min_needed:
        return legacy[-18:], None, "4h", chart_days

    if not allow_live_fetch:
        if saved:
            return [], f"저장된 캔들 부족 ({len(saved)}개)", chart_interval, chart_days
        return [], "저장된 캔들 없음 — 새로고침 후에도 안 되면 재배포가 필요합니다", chart_interval, chart_days

    live = get_coin_candles(symbol, interval=chart_interval, limit=limit)
    if len(live) >= min_needed:
        return live, None, chart_interval, chart_days
    if saved:
        return [], f"캔들 부족 (저장 {len(saved)}개, 실시간 {len(live)}개)", chart_interval, chart_days
    return [], f"캔들 데이터 없음 (실시간 {len(live)}개)", chart_interval, chart_days