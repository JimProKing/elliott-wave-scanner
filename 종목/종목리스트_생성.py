"""
종목리스트_생성.py

바이낸스 거래 가능한 종목 목록을 txt 파일로 생성하는 전용 스크립트.

실행하면:
- 현재 시각 기준으로 ` 종목/YYYYMMDD_HHMM_종목들.txt ` 파일 생성 (이 파일은 바이낸스/종목/ 안에 위치)
- 전체 USDT 페어를 24h 거래량(quoteVolume) 내림차순으로 정렬
- 상위 100개에 대해서는 분류 + 매수/매도 비율 + 거래량이 추가로 기록

사용법:
    python 바이낸스/종목/종목리스트_생성.py
"""

import sys
import os
import time
from pathlib import Path
from datetime import datetime
from typing import List, Tuple

# -------------------------------------------------
# binance_utils 임포트 (프로젝트 구조 고려)
# 이제 종목/ 폴더가 바이낸스/ 안에 있음
# __file__ = .../바이낸스/종목/종목리스트_생성.py
# binance_path = .../바이낸스/
# -------------------------------------------------
script_dir = Path(__file__).parent          # 바이낸스/종목
binance_path = script_dir.parent            # 바이낸스
sys.path.insert(0, str(binance_path))

from binance_utils import get_all_tradable_symbols, get_24h_tickers, get_klines


# -----------------------------
# 분류 기준 (하드코딩 + 간단 휴리스틱)
# -----------------------------
USD_STABLES: set = {
    "USDT", "USDC", "FDUSD", "USDD", "TUSD", "BUSD", "USD1",
    "USDP", "GUSD", "DAI", "FRAX", "USTC",
    "PYUSD", "RLUSD", "USDE", "sUSDe", "USDS", "AUSD"
}

BOND_KEYWORDS: List[str] = ["BOND", "BILL", "TREAS", "NOTE", "DEBT", "FIXED", "YIELD"]


def classify_symbol(symbol: str) -> str:
    """
    심볼을 간단한 규칙으로 분류.
    반환값: "달러 스테이블", "채권", "코인"
    """
    if not symbol.endswith("USDT"):
        return "기타"

    base = symbol[:-4].upper()   # "BTCUSDT" → "BTC"

    if base in USD_STABLES:
        return "달러 스테이블"

    if any(kw in base for kw in BOND_KEYWORDS):
        return "채권"

    # 그 외는 모두 코인 (메이저/알트/밍 등 구분은 생략, 필요시 확장 가능)
    return "코인"


def generate_symbol_list() -> str:
    """
    실제 목록 생성 + 파일 저장.
    반환값: 생성된 파일의 전체 경로
    """
    print("[1] 거래 가능한 종목 조회 중...")
    tradable_set = set(get_all_tradable_symbols(quote=None))
    print(f"    전체 거래 가능 종목: {len(tradable_set)}개")

    print("[2] 24h 티커(거래량) 조회 중...")
    tickers = get_24h_tickers()

    volume_list: List[Tuple[str, float, float]] = []
    for t in tickers:
        sym = t.get("symbol", "")
        if sym in tradable_set and sym.endswith("USDT"):
            try:
                qvol = float(t.get("quoteVolume", 0) or 0)
                buy_qvol = float(t.get("takerBuyQuoteAssetVolume", 0) or 0)
            except (ValueError, TypeError):
                qvol = 0.0
                buy_qvol = 0.0
            volume_list.append((sym, qvol, buy_qvol))

    # 거래량 높은 순 정렬
    volume_list.sort(key=lambda x: x[1], reverse=True)
    sorted_symbols = [item[0] for item in volume_list]

    print(f"    USDT 페어 {len(sorted_symbols)}개 (거래량 기준 정렬 완료)")

    # 출력 디렉토리 (이 스크립트가 있는 종목/ 폴더)
    output_dir = Path(__file__).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    # 타임스탬프 파일명
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M")
    filename = f"{timestamp}_종목들.txt"
    filepath = output_dir / filename

    # 상위 100개에 대해 kline으로 매수/매도 비율 계산 (ticker의 taker 필드가 환경에 따라 제공되지 않음)
    print("    상위 100개 매수/매도 비율 계산 중 (1h klines 집계)...")
    buy_ratios = {}
    top_for_calc = volume_list[:100]
    for sym, _, _ in top_for_calc:
        try:
            candles = get_klines(sym, interval="1h", limit=24)
            total_q = sum((c.get("quoteVolume") or 0) for c in candles)
            buy_q = sum((c.get("takerBuyQuoteAssetVolume") or 0) for c in candles)
            buy_ratios[sym] = (buy_q / total_q * 100) if total_q > 0 else 50.0
            time.sleep(0.03)
        except Exception:
            buy_ratios[sym] = 50.0

    # 파일 작성
    with open(filepath, "w", encoding="utf-8") as f:
        # 헤더
        f.write("# Binance Spot 거래 가능한 종목 목록 (USDT 페어)\n")
        f.write("# 정렬: 24시간 거래량(quoteVolume) 높은 순\n")
        f.write(f"# 생성일시: {now.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"# 총 종목 수: {len(sorted_symbols)}\n")
        f.write("#\n")
        f.write("# 참고: 상위 100개는 파일 상단에 분류 + 매수/매도 비율 + 24h 거래량(USDT)이 포함됩니다.\n")
        f.write("#\n")

        # 상위 100개 분류 섹션 (위로 이동)
        f.write("# =============================================\n")
        f.write("# 거래량 상위 100개 (분류 + 매수/매도 비율 + 거래량)\n")
        f.write("# =============================================\n")
        f.write("# 형식: 순위. 심볼 | 분류 | 매수 XX.X% | 매도 XX.X% | 거래량 $XXXM\n")
        f.write("#\n")

        top_n = min(100, len(volume_list))
        for i, (sym, qvol, _) in enumerate(volume_list[:top_n], 1):
            category = classify_symbol(sym)
            buy_pct = buy_ratios.get(sym, 50.0)
            sell_pct = 100 - buy_pct
            vol_str = f"${qvol/1_000_000:,.1f}M"
            f.write(f"{i}. {sym} | {category} | 매수 {buy_pct:.1f}% | 매도 {sell_pct:.1f}% | 거래량 {vol_str}\n")

        # 빈 줄 구분
        f.write("\n\n")

        # 전체 종목 명단 (한 줄에 하나, 하단에 배치)
        f.write("# 전체 종목 목록 (거래량 높은 순)\n")
        for sym in sorted_symbols:
            f.write(sym + "\n")

    return str(filepath)


if __name__ == "__main__":
    print("=" * 55)
    print("Binance 종목 리스트 생성기 (전용 스크립트)")
    print("=" * 55)

    try:
        output_path = generate_symbol_list()
        print(f"\n✅ 파일 생성 완료: {output_path}")

        # 간단 미리보기
        print("\n[\uc0c1위 10개 미리보기]")
        # 재사용을 위해 간단히 다시 로드하지 않고, 위 로직에서 이미 정렬된 상태이므로
        # 여기서는 파일이 생성되었음을 알리고, 사용자가 파일을 직접 확인하도록 유도
        print("   (자세한 상위 100개 분류는 생성된 txt 파일의 상단 섹션을 확인하세요)")

    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        raise

    print("\n완료.")