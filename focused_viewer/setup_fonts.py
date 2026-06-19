#!/usr/bin/env python3
"""차트용 한글 폰트 확인/다운로드 (Render Linux 빌드용)."""

from __future__ import annotations

import urllib.request
from pathlib import Path

FONT_DIR = Path(__file__).resolve().parent / "fonts"
FONT_FILE = FONT_DIR / "NotoSansKR.ttf"
FONT_URL = (
    "https://raw.githubusercontent.com/google/fonts/main/ofl/notosanskr/"
    "NotoSansKR%5Bwght%5D.ttf"
)


def ensure_font() -> Path:
    if FONT_FILE.exists() and FONT_FILE.stat().st_size > 1_000_000:
        return FONT_FILE

    FONT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[fonts] downloading {FONT_FILE.name}...")
    urllib.request.urlretrieve(FONT_URL, FONT_FILE)
    print(f"[fonts] saved {FONT_FILE.stat().st_size:,} bytes")
    return FONT_FILE


def main() -> int:
    ensure_font()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())