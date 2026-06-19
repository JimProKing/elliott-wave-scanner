#!/usr/bin/env python3
"""GitHub Actions / cron용 지정종목 분석 실행 스크립트."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))

from analyzer_bridge import run_analysis  # noqa: E402

DATA_FILE = APP_DIR / "data" / "latest.json"


def main() -> int:
    result = run_analysis(interval="4h", lookback=110, save=False)
    if not result.get("results"):
        print("분석 결과 없음")
        return 1

    payload = {
        "generated_at": result["generated_at"],
        "interval": result["interval"],
        "lookback": result["lookback"],
        "coins": [r["kr"] for r in result["results"]],
        "results": result["results"],
        "updated_by": "github-actions",
    }

    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"저장 완료: {DATA_FILE} ({len(result['results'])}종목)")
    print(f"생성 시각: {datetime.now().isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())