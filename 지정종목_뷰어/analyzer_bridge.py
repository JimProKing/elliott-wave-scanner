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
    TARGET_COINS,
    fetch_klines,
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
    return data


def save_to_data_file(payload: Dict) -> Path:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return _DATA_FILE


def run_analysis(interval: str = "4h", lookback: int = 110, save: bool = True) -> Dict:
    results = run_focused_analysis(interval=interval, lookback=lookback)
    saved_path = None

    payload = {
        "generated_at": datetime.now().isoformat(),
        "interval": interval,
        "lookback": lookback,
        "coins": [c["kr"] for c in TARGET_COINS],
        "results": results,
    }

    if results:
        save_to_data_file(payload)
        if save and not os.environ.get("WEB_DEPLOY"):
            saved_path = str(save_reports(results))

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