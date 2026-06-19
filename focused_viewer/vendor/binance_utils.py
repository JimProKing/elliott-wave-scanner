"""
Binance Spot Market Utilities (공개 API 사용, API 키 불필요)

1. get_all_tradable_symbols(quote=None) -> List[str]
   - 거래 가능한 모든 심볼 리스트 반환 (기본: 전체 TRADING 심볼)
   - quote="USDT" 로 필터링하면 USDT 페어만 반환

2. get_current_price(symbol) -> float | None
   - 심볼(예: BTCUSDT, XRPUSDT, BTC/USDT 등) 현재 시장가 반환

3. get_klines / get_24h_tickers / calculate_rsi
   - 고급 분석(예: Elliott Wave 스캐너)을 위한 기반 유틸리티

고급 분석 기능은 별도 파일(elliott_wave_scanner.py 등)로 분리되어 있습니다.
"""

import urllib.request
import json
import time
from typing import List, Optional, Dict


BASE_URL = "https://api.binance.com"


def _fetch_json(url: str, max_retries: int = 2) -> dict:
    """내부용: Binance REST 호출 + 간단 재시도"""
    headers = {"User-Agent": "python-trading-utils/1.0"}
    last_err = None

    for attempt in range(max_retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=12) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw)
        except Exception as e:
            last_err = e
            if attempt < max_retries:
                time.sleep(0.6 * (attempt + 1))
            else:
                raise RuntimeError(f"Binance API 호출 실패: {url} | {last_err}") from last_err


def normalize_symbol(symbol: str) -> str:
    """심볼 정규화: BTC/USDT, btc-usdt, btcusdt → BTCUSDT"""
    if not symbol:
        raise ValueError("심볼이 비어 있습니다.")
    s = symbol.upper().strip()
    s = s.replace("/", "").replace("-", "").replace("_", "")
    # 간단 검증 (너무 짧은 경우)
    if len(s) < 4 or len(s) > 20:
        raise ValueError(f"유효하지 않은 심볼 형식입니다: {symbol}")
    return s


def get_all_tradable_symbols(quote: Optional[str] = None) -> List[str]:
    """
    바이낸스 스팟(Spot)에서 거래 가능한(TRADING 상태) 모든 심볼 리스트를 반환합니다.

    Args:
        quote: 필터 (예: "USDT", "BTC", "ETH"). None이면 전체 반환.

    Returns:
        정렬된 심볼 리스트 (예: ["BTCUSDT", "ETHUSDT", ...])

    Example:
        >>> symbols = get_all_tradable_symbols(quote="USDT")
        >>> len(symbols) > 100
        True
        >>> "BTCUSDT" in symbols
        True
    """
    url = f"{BASE_URL}/api/v3/exchangeInfo"
    data = _fetch_json(url)

    symbols: List[str] = []
    for s in data.get("symbols", []):
        if s.get("status") != "TRADING":
            continue
        # Spot 거래 허용 여부도 확인 (대부분 True지만 안전하게)
        if not s.get("isSpotTradingAllowed", True):
            continue

        sym = s["symbol"]
        if quote is None or s.get("quoteAsset") == quote.upper():
            symbols.append(sym)

    return sorted(symbols)


def get_current_price(symbol: str) -> Optional[float]:
    """
    특정 심볼의 현재 시장 가격(Last Price)을 반환합니다.

    Args:
        symbol: "BTCUSDT", "XRPUSDT", "ETH/BTC" 등 (자동 정규화)

    Returns:
        float 가격 (예: 67234.56). 실패 시 None.

    Example:
        >>> price = get_current_price("BTCUSDT")
        >>> price is None or price > 0
        True
    """
    try:
        norm = normalize_symbol(symbol)
        url = f"{BASE_URL}/api/v3/ticker/price?symbol={norm}"
        data = _fetch_json(url)
        price_str = data.get("price")
        if price_str is None:
            return None
        return float(price_str)
    except Exception as e:
        print(f"[오류] {symbol} 가격 조회 실패: {e}")
        return None


def get_multiple_prices(symbols: List[str]) -> Dict[str, Optional[float]]:
    """
    여러 심볼의 가격을 한 번에 조회 (편의 함수).
    """
    result: Dict[str, Optional[float]] = {}
    for sym in symbols:
        result[sym] = get_current_price(sym)
        time.sleep(0.05)  # rate limit 배려 (가벼운 호출)
    return result


def get_24h_tickers() -> List[Dict]:
    """전체 심볼 24시간 티커 정보 (volume, priceChangePercent 등)."""
    url = f"{BASE_URL}/api/v3/ticker/24hr"
    return _fetch_json(url)


def get_klines(symbol: str, interval: str = "4h", limit: int = 100) -> List[Dict[str, float]]:
    """
    바이낸스 캔들(OHLCV) 데이터 조회.

    Args:
        symbol: "BTCUSDT" 등
        interval: "1h", "4h", "1d" 등
        limit: 최대 1000, 일반적으로 80~150 사용
    """
    norm = normalize_symbol(symbol)
    url = f"{BASE_URL}/api/v3/klines?symbol={norm}&interval={interval}&limit={limit}"
    raw = _fetch_json(url)
    candles: List[Dict[str, float]] = []
    for row in raw:
        candles.append({
            "open_time": int(row[0]),
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[5]),
            "close_time": int(row[6]),
            "quoteVolume": float(row[7]),
            "numTrades": int(row[8]),
            "takerBuyBaseAssetVolume": float(row[9]),
            "takerBuyQuoteAssetVolume": float(row[10]),
        })
    return candles


def calculate_rsi(closes: List[float], period: int = 14) -> Optional[float]:
    """단순 RSI (마지막 값만 반환). Wilder's smoothing은 생략한 경량 버전."""
    if len(closes) < period + 1:
        return None
    gains: List[float] = []
    losses: List[float] = []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        if delta > 0:
            gains.append(delta)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(-delta)
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


# ---------------------------
# 사용 예시 (직접 실행 시)
# ---------------------------
if __name__ == "__main__":
    print("=" * 50)
    print("Binance Utils 기본 테스트")
    print("=" * 50)

    # USDT 종목 수 확인
    usdt_pairs = get_all_tradable_symbols(quote="USDT")
    print(f"\n[1] 거래 가능한 USDT 페어 수: {len(usdt_pairs)}")
    print("    예시:", usdt_pairs[:8])

    # 현재가 조회
    test_symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
    print("\n[2] 현재 시장가:")
    for sym in test_symbols:
        price = get_current_price(sym)
        if price is not None:
            fmt = f"{price:,.2f}" if price >= 1000 else (f"{price:,.4f}" if price >= 1 else f"{price:.8f}")
            print(f"    {sym:12} : {fmt}")
        else:
            print(f"    {sym:12} : 조회 실패")

    # Klines + RSI 간단 데모
    print("\n[3] Klines + RSI 데모 (BTCUSDT)")
    try:
        candles = get_klines("BTCUSDT", interval="4h", limit=30)
        closes = [c["close"] for c in candles]
        rsi = calculate_rsi(closes, 14)
        print(f"    캔들 수: {len(closes)}")
        print(f"    마지막 RSI(14): {rsi:.2f}" if rsi else "    RSI: N/A")
        print(f"    마지막 종가: {closes[-1]:.2f}")
    except Exception as e:
        print(f"    조회 실패: {e}")

    print("\n(종목 목록 txt 생성은 바이낸스/종목/종목리스트_생성.py 를 실행하세요)")
    print("완료.")
