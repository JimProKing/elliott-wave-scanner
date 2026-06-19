#!/usr/bin/env python3
"""
엘리어트 파동 이론 기반 지정종목 상승/하락 분석 프로그램 (Focused Elliott Analyzer)

대상 종목:
- 바이낸스 USDT 페어 중 당일 24h 거래량(quote volume) 상위 N개 (기본 20)
- 스테이블코인·레버리지 토큰 제외

목표:
- 기존 범용 스캐너의 "구림" 문제 해결: 좁은 대상 + 상승+하락 양방향 + 더 이론 준수 규칙 기반 분석
- **직관적 점수 중심 출력** (80점 이상 = ★★★★★ 강력 매수/롱 또는 숏 추천)
- 각 종목당 명확한 bullish / bearish 구조 평가 + 점수 + 추천 문구 + 이유 + 핵심 레벨 제공
- 4h (주요) + 1d (컨텍스트) 멀티 타임프레임 + 멀티TF 보너스
- 고전 Elliott 규칙 최대한 반영 (Wave2 38.2-78.6%, Wave3 not shortest, impulse 강도 등)
- 실전 참고용 레벨: Entry / TP (1.618 / 2.0 / 2.618) / SL (invalidation)

주의: 이는 규칙 기반 휴리스틱 분석 도구입니다. 실제 매매 결정 전 상위 타임프레임 차트 + 본인 판단 + 리스크 관리 필수.
"""

import sys
import time
import json
import math
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# binance_utils 임포트 (기존 프로젝트 유틸 재사용)
try:
    from binance_utils import get_24h_tickers, get_klines as binance_get_klines, calculate_rsi
except ImportError:
    current_dir = Path(__file__).parent
    if str(current_dir) not in sys.path:
        sys.path.insert(0, str(current_dir))
    from binance_utils import get_24h_tickers, get_klines as binance_get_klines, calculate_rsi


# ============================================================
# 대상 종목 (당일 거래량 상위)
# ============================================================
DEFAULT_TOP_N = 20

STABLE_BASES = frozenset({
    "USDC", "FDUSD", "TUSD", "USDE", "DAI", "EUR", "AEUR", "USD1", "USDP", "BUSD", "USDS", "EURI",
    "RLUSD", "U", "USD", "USDD",
})

LEVERAGED_SUFFIXES = ("UP", "DOWN", "BULL", "BEAR")


def _is_leveraged_token(base: str) -> bool:
    return any(base.endswith(suffix) and len(base) > len(suffix) + 1 for suffix in LEVERAGED_SUFFIXES)


def get_top_volume_coins(top_n: int = DEFAULT_TOP_N) -> List[Dict]:
    """바이낸스 USDT 페어 24h 거래량 상위 N개."""
    tickers = get_24h_tickers()
    pairs: List[Tuple[str, str, float]] = []

    for t in tickers:
        sym = t.get("symbol", "")
        if not sym.endswith("USDT"):
            continue
        base = sym[:-4]
        if base in STABLE_BASES:
            continue
        if _is_leveraged_token(base):
            continue
        try:
            vol = float(t.get("quoteVolume", 0))
            if vol <= 0:
                continue
            pairs.append((sym, base, vol))
        except (TypeError, ValueError):
            continue

    pairs.sort(key=lambda x: x[2], reverse=True)

    coins: List[Dict] = []
    for rank, (sym, base, vol) in enumerate(pairs[:top_n], start=1):
        coins.append({
            "kr": base,
            "sym": sym,
            "name": base,
            "volume_24h": vol,
            "volume_rank": rank,
        })
    return coins


# 하위 호환 alias (실제 분석은 get_top_volume_coins() 사용)
TARGET_COINS: List[Dict] = []

# ============================================================
# 데이터 페치 (Binance + CoinGecko CONX 지원)
# ============================================================
def fetch_klines(symbol: str, interval: str = "4h", limit: int = 120) -> List[Dict]:
    """
    통합 캔들 페치.
    - 일반: Binance
    - CONX: CoinGecko ohlc (무료, granularity는 days에 따라 다름. 구조 분석에는 충분)
    반환 형식은 binance_get_klines와 동일하게 open/high/low/close/volume 포함.
    """
    upper = symbol.upper()
    if "CONX" in upper or upper == "CONX":
        return _fetch_coingecko_ohlc(coin_id="connex", days=30, target_limit=limit)

    # Binance
    try:
        candles = binance_get_klines(symbol, interval=interval, limit=limit)
        return candles
    except Exception as e:
        print(f"  [경고] {symbol} Binance 데이터 실패: {e}")
        return []


def _fetch_coingecko_ohlc(coin_id: str, days: int = 30, target_limit: int = 120) -> List[Dict]:
    """
    CoinGecko /ohlc : [[time_ms, o, h, l, c], ...]
    volume 없음. 구조 분석용으로 close sequence 사용.
    granularity: days=30 기준 보통 4h~1d 수준 (종목 따라 상이). 분석 함수는 캔들 순서만 중요.
    """
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc?vs_currency=usd&days={days}&precision=4"
    headers = {"User-Agent": "focused-elliott-analyzer/1.0"}
    try:
        import urllib.request
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        candles: List[Dict] = []
        for row in raw[-target_limit:]:  # 최근 N개
            candles.append({
                "open_time": int(row[0]),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": 0.0,  # CG free tier는 volume 미제공
            })
        # 간단히 시간순 정렬 보장 (CG는 오래된->최신)
        candles.sort(key=lambda x: x["open_time"])
        return candles
    except Exception as e:
        print(f"  [경고] CoinGecko {coin_id} 데이터 실패: {e}")
        return []


def fetch_daily_context(symbol: str) -> List[Dict]:
    """1d 컨텍스트용 (Binance는 1d, CONX는 CG days=90으로 대략 일봉 추출)"""
    if "CONX" in symbol.upper():
        # CG에서 더 많은 days로 가져와서 최근 60개 정도 사용 (대략 일봉에 가까운 포인트)
        c = _fetch_coingecko_ohlc("connex", days=90, target_limit=90)
        return c[-60:] if len(c) > 60 else c
    try:
        return binance_get_klines(symbol, interval="1d", limit=80)
    except Exception:
        return []


# ============================================================
# 스윙 탐지 (기존 개선형 + 약간 강화)
# ============================================================
def _find_recent_swings(closes: List[float], window: int = 3, min_move_pct: float = 0.012) -> List[Dict]:
    """
    의미 있는 스윙만 추출.
    - window=3: 노이즈 억제
    - min_move_pct: 1.2% 이상 이동만 의미 있는 것으로 간주 (작은 wiggle 제거)
    """
    raw: List[Dict] = []
    n = len(closes)
    for i in range(window, n - window):
        is_high = all(closes[i] > closes[i - k] for k in range(1, window + 1)) and \
                  all(closes[i] > closes[i + k] for k in range(1, window + 1))
        is_low = all(closes[i] < closes[i - k] for k in range(1, window + 1)) and \
                 all(closes[i] < closes[i + k] for k in range(1, window + 1))
        if is_high:
            raw.append({"idx": i, "price": closes[i], "type": "high"})
        elif is_low:
            raw.append({"idx": i, "price": closes[i], "type": "low"})

    if not raw:
        return []

    filtered: List[Dict] = [raw[0]]
    for s in raw[1:]:
        prev = filtered[-1]["price"]
        move = abs(s["price"] - prev) / prev if prev > 0 else 0
        if move >= min_move_pct:
            filtered.append(s)
    return filtered


# ============================================================
# 핵심: 상승 + 하락 양방향 엘리어트 분석 (개선판)
# ============================================================
def analyze_elliott_bullish(candles: List[Dict]) -> Dict:
    """
    상승 Impulse (특히 Wave 3 시작/진행) 가능성 분석.
    고전 규칙:
    - Wave 2: 38.2~78.6% 되돌림 (절대 100% 초과 금지)
    - Wave 3: Wave1보다 길고 강력해야 함 (not the shortest)
    - 최근 고점 돌파 + impulse candle + retrace 품질
    """
    if len(candles) < 35:
        return {"score": 0, "label": "데이터 부족", "reasons": ["캔들 부족 (최소 35 필요)"], "bullish": False}

    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    opens = [c.get("open", c["close"]) for c in candles]
    vols = [c.get("volume", 0) for c in candles]
    current_price = closes[-1]
    rsi = calculate_rsi(closes, 14)

    swings = _find_recent_swings(closes, window=3, min_move_pct=0.012)
    score = 12
    reasons: List[str] = []
    label = "불명확 / 조정 중"

    if len(swings) < 3:
        return {"score": min(28, score), "label": label, "reasons": ["의미 있는 스윙 부족"], "bullish": False,
                "rsi": rsi, "price": round(current_price, 6)}

    recent = swings[-7:] if len(swings) >= 7 else swings

    # HH/HL 구조 강도 (더 직관적 고득점)
    hh_hl = 0
    last_h = last_l = None
    for s in recent:
        if s["type"] == "high":
            if last_h is None or s["price"] > last_h:
                hh_hl += 1
            last_h = s["price"]
        else:
            if last_l is None or s["price"] > last_l:
                hh_hl += 1
            last_l = s["price"]

    if hh_hl >= 5:
        score += 20
        reasons.append("Higher High + Higher Low 강한 연속 구조 (청정 impulse 진행)")
    elif hh_hl >= 4:
        score += 12
        reasons.append("Higher High + Higher Low 양호한 구조")

    # Wave 2 스타일 되돌림 품질 (가장 최근 의미 있는 up leg 직후 pullback)
    best_retrace = 0.0
    retrace_low = None
    for i in range(1, len(recent)):
        if recent[i-1]["type"] == "high" and recent[i]["type"] == "low":
            prev = recent[i-2]["price"] if i >= 2 else recent[i-1]["price"] * 0.88
            leg = recent[i-1]["price"] - prev
            pull = recent[i-1]["price"] - recent[i]["price"]
            if leg > 0:
                retr = pull / leg
                if 0.30 <= retr <= 0.82 and retr > best_retrace:
                    best_retrace = retr
                    retrace_low = recent[i]["price"]

    if 0.382 <= best_retrace <= 0.786:
        score += 18
        reasons.append(f"Wave 2 유효 조정 {best_retrace*100:.1f}% (38.2~78.6% 피보나치 존 - 고전 규칙 충족)")
        if 0.50 <= best_retrace <= 0.618:
            score += 10   # textbook sweet spot 보너스
            reasons.append("완벽한 50~61.8% 조정 (Wave 3 강세 기대 최대 구간)")
    elif 0.25 <= best_retrace < 0.382:
        score += 8
        reasons.append(f"얕은 조정 {best_retrace*100:.1f}% (Wave 3 가능성 있지만 약할 수 있음)")
    elif best_retrace > 0.82:
        score -= 6
        reasons.append(f"과도 조정 {best_retrace*100:.1f}% (Wave 2 규칙 위반 위험)")

    # Wave 1 고점 돌파 (Wave 3 트리거)
    last_high = None
    last_high_idx = None
    for s in reversed(recent):
        if s["type"] == "high":
            last_high = s["price"]
            last_high_idx = s["idx"]
            break

    breakout_bars = 99
    if last_high and current_price > last_high * 1.004:
        breakout_bars = len(closes) - 1 - last_high_idx if last_high_idx is not None else 30
        if breakout_bars <= 3:
            score += 26
        elif breakout_bars <= 4:
            score += 22
        elif breakout_bars <= 9:
            score += 16
        else:
            score += 9
        label = "Wave 3 진행 또는 시작"
        reasons.append(f"이전 고점 돌파 (경과 {breakout_bars}봉) - Wave 3 impulse 개시 신호")

        # Impulse candle 확인
        last_c = candles[-1]
        body = last_c["close"] - last_c["open"]
        rng = max(0.0001, last_c["high"] - last_c["low"])
        if body / rng >= 0.40:
            score += 6
            reasons.append("강한 impulse 캔들 동반")

    # Wave 3 확장 / 강도 (retrace 저점 대비)
    leg_ext = 0.0
    if retrace_low and retrace_low > 0:
        leg_ext = (current_price - retrace_low) / (last_high - retrace_low) if last_high and last_high > retrace_low else 0
        if leg_ext > 1.0:
            score += 7
            reasons.append("Wave 1 크기 초과 상승 (이론적 Wave 3 강세 특징)")
        elif leg_ext > 0.6:
            score += 3

    # 과도 연장 페널티 (늦은 진입 방지)
    if retrace_low and retrace_low > 0:
        run = (current_price - retrace_low) / max(0.0001, last_high - retrace_low) if last_high else 0
        if run > 1.35:
            score -= 10
            reasons.append("Wave 2 저점 대비 과도 연장 (이미 많이 달린 상태 - Wave 3 후반 또는 5 가능성)")
        elif run > 0.95:
            score -= 4

    # RSI
    if rsi is not None:
        if 44 <= rsi <= 68:
            score += 6
            reasons.append(f"RSI {rsi:.0f} (Wave 3 시작에 적합한 모멘텀 구간)")
        elif rsi < 38:
            score += 4
        elif rsi > 78:
            score -= 6
            reasons.append(f"RSI {rsi:.0f} (과매수 - Wave 3 초기 부적합 위험)")

    # 최근 가속
    if len(closes) >= 10:
        accel = (current_price - closes[-6]) / max(0.0001, closes[-6])
        if accel > 0.055:
            score += 5
            reasons.append("최근 6봉 내 강한 가속")

    # Textbook Impulse 보너스 (여러 조건 동시 충족 시 고득점 → 80점대 가능하게)
    textbook = 0
    if hh_hl >= 5 and 0.50 <= best_retrace <= 0.618 and breakout_bars <= 5:
        textbook += 8
    if "Wave 2 유효 조정" in " | ".join(reasons) and "이전 고점 돌파" in " | ".join(reasons) and "강한 impulse" in " | ".join(reasons):
        textbook += 6
    if textbook > 0:
        score += textbook
        reasons.append("여러 Elliott 규칙 동시 충족 (Textbook Impulse)")

    score = max(3, min(100, int(score)))

    if score >= 80:
        if "Wave 3" not in label:
            label = "강력 상승 Impulse (고신뢰도)"
        is_bull = True
    elif score >= 70:
        if "Wave 3" not in label:
            label = "강한 상승 Impulse"
        is_bull = True
    elif score >= 60:
        label = "상승 Impulse Setup"
        is_bull = True
    elif score >= 50:
        label = "약한 상승 신호"
        is_bull = False
    else:
        is_bull = False

    meta = {}
    if retrace_low:
        meta["retrace_pct"] = round(best_retrace * 100, 1)
        meta["leg_from_w2_low_pct"] = round((current_price - retrace_low) / retrace_low * 100, 1) if retrace_low else 0
    if last_high:
        meta["breakout_pct"] = round((current_price - last_high) / last_high * 100, 1)

    return {
        "score": score,
        "label": label,
        "reasons": reasons[:5],
        "bullish": is_bull,
        "rsi": rsi,
        "price": round(current_price, 6),
        "meta": meta,
        "swings": recent[-4:],
    }


def analyze_elliott_bearish(candles: List[Dict]) -> Dict:
    """
    하락 Impulse (특히 Wave 3 down 또는 C파) 가능성 분석.
    상승 로직의 대칭 버전.
    """
    if len(candles) < 35:
        return {"score": 0, "label": "데이터 부족", "reasons": ["캔들 부족"], "bearish": False}

    closes = [c["close"] for c in candles]
    opens = [c.get("open", c["close"]) for c in candles]
    vols = [c.get("volume", 0) for c in candles]
    current_price = closes[-1]
    rsi = calculate_rsi(closes, 14)

    swings = _find_recent_swings(closes, window=3, min_move_pct=0.012)
    score = 15
    reasons: List[str] = []
    label = "불명확 / 반등 중 또는 조정"

    if len(swings) < 3:
        return {"score": min(28, score), "label": label, "reasons": ["의미 있는 스윙 부족"], "bearish": False,
                "rsi": rsi, "price": round(current_price, 6)}

    recent = swings[-7:] if len(swings) >= 7 else swings

    # Lower High + Lower Low 구조
    lh_ll = 0
    last_h = last_l = None
    for s in recent:
        if s["type"] == "low":
            if last_l is None or s["price"] < last_l:
                lh_ll += 1
            last_l = s["price"]
        else:
            if last_h is None or s["price"] < last_h:
                lh_ll += 1
            last_h = s["price"]

    if lh_ll >= 5:
        score += 20
        reasons.append("Lower High + Lower Low 강한 연속 구조 (청정 하락 impulse)")
    elif lh_ll >= 4:
        score += 12
        reasons.append("Lower High + Lower Low 양호한 구조")

    # Wave 2 스타일 반등 (하락 Wave1 후의 retrace up)
    best_retrace = 0.0
    retrace_high = None
    for i in range(1, len(recent)):
        if recent[i-1]["type"] == "low" and recent[i]["type"] == "high":
            prev = recent[i-2]["price"] if i >= 2 else recent[i-1]["price"] * 1.12
            leg_down = prev - recent[i-1]["price"]
            retr_up = recent[i]["price"] - recent[i-1]["price"]
            if leg_down > 0:
                retr = retr_up / leg_down
                if 0.30 <= retr <= 0.82 and retr > best_retrace:
                    best_retrace = retr
                    retrace_high = recent[i]["price"]

    if 0.382 <= best_retrace <= 0.786:
        score += 18
        reasons.append(f"하락 Wave 2 유효 반등 {best_retrace*100:.1f}% (피보나치 존)")
        if 0.50 <= best_retrace <= 0.618:
            score += 10
            reasons.append("완벽한 50~61.8% 반등 (하락 C파 또는 Wave 3 강세 기대)")
    elif best_retrace > 0.82:
        score -= 6
        reasons.append(f"과도 반등 {best_retrace*100:.1f}% (하락 impulse 규칙 위반 위험)")

    # 저점 하회 (하락 Wave 3 트리거)
    last_low = None
    last_low_idx = None
    for s in reversed(recent):
        if s["type"] == "low":
            last_low = s["price"]
            last_low_idx = s["idx"]
            break

    breakout_bars = 99
    if last_low and current_price < last_low * 0.996:
        breakout_bars = len(closes) - 1 - last_low_idx if last_low_idx is not None else 30
        if breakout_bars <= 3:
            score += 26
        elif breakout_bars <= 4:
            score += 22
        elif breakout_bars <= 9:
            score += 16
        else:
            score += 9
        label = "하락 Wave 3 진행 또는 시작"
        reasons.append(f"이전 저점 하회 (경과 {breakout_bars}봉) - 하락 impulse 개시")

        # 강한 하락 캔들
        last_c = candles[-1]
        body = last_c["open"] - last_c["close"]
        rng = max(0.0001, last_c["high"] - last_c["low"])
        if body / rng >= 0.40:
            score += 6
            reasons.append("강한 하락 impulse 캔들 동반")

    # 과도 하락 페널티
    if retrace_high and retrace_high > 0 and last_low:
        run = (retrace_high - current_price) / max(0.0001, retrace_high - last_low)
        if run > 1.35:
            score -= 10
            reasons.append("과도 하락 연장 (이미 많이 떨어짐 - 반등 주의)")

    # RSI (하락 시 낮은 RSI가 impulse 지속에 유리)
    if rsi is not None:
        if 32 <= rsi <= 52:
            score += 6
            reasons.append(f"RSI {rsi:.0f} (하락 impulse에 적합한 모멘텀)")
        elif rsi > 68:
            score -= 5
            reasons.append(f"RSI {rsi:.0f} (과매수 - 하락 전환에 불리)")

    # Textbook 하락 Impulse 보너스
    textbook = 0
    if lh_ll >= 5 and 0.50 <= best_retrace <= 0.618 and breakout_bars <= 5:
        textbook += 8
    if "하락 Wave 2 유효 반등" in " | ".join(reasons) and "이전 저점 하회" in " | ".join(reasons) and "강한 하락 impulse" in " | ".join(reasons):
        textbook += 6
    if textbook > 0:
        score += textbook
        reasons.append("여러 Elliott 규칙 동시 충족 (Textbook 하락 Impulse)")

    score = max(3, min(100, int(score)))

    if score >= 80:
        if "Wave 3" not in label:
            label = "강력 하락 Impulse (고신뢰도)"
        is_bear = True
    elif score >= 70:
        if "Wave 3" not in label:
            label = "강한 하락 Impulse"
        is_bear = True
    elif score >= 60:
        label = "하락 Impulse Setup"
        is_bear = True
    elif score >= 50:
        label = "약한 하락 신호"
        is_bear = False
    else:
        is_bear = False

    meta = {}
    if best_retrace:
        meta["retrace_pct"] = round(best_retrace * 100, 1)
    if last_low:
        meta["breakdown_pct"] = round((last_low - current_price) / last_low * 100, 1) if last_low else 0

    return {
        "score": score,
        "label": label,
        "reasons": reasons[:5],
        "bearish": is_bear,
        "rsi": rsi,
        "price": round(current_price, 6),
        "meta": meta,
        "swings": recent[-4:],
    }


def get_higher_tf_bias(daily_candles: List[Dict]) -> str:
    """간단한 일봉 컨텍스트: 가격 위치 + 구조"""
    if len(daily_candles) < 20:
        return "컨텍스트 부족"
    closes = [c["close"] for c in daily_candles]
    current = closes[-1]
    sma20 = sum(closes[-20:]) / 20
    sma50 = sum(closes[-min(50, len(closes)):]) / min(50, len(closes)) if len(closes) >= 25 else sma20

    if current > sma20 > sma50:
        return "상승 우위 (일봉 20/50 위)"
    elif current < sma20 < sma50:
        return "하락 우위 (일봉 20/50 아래)"
    else:
        return "중립 / 박스 (일봉 혼조)"


def compute_levels(current: float, swing_low: Optional[float], swing_high: Optional[float], direction: str) -> Dict:
    """
    방향에 따른 실전 레벨 계산 (Elliott + Fib)
    - Long: SL = 최근 의미 저점 약간 아래, TP = 1.618R / 2.0R / 2.618R
    - Short: 대칭
    """
    if direction == "long":
        sl = round(swing_low * 0.982, 8) if swing_low else round(current * 0.94, 8)
        if sl >= current:
            sl = round(current * 0.93, 8)
        risk = current - sl
        tps = [round(current + risk * r, 8) for r in (1.618, 2.0, 2.618)]
        return {"entry": round(current, 8), "sl": sl, "tp1": tps[0], "tp2": tps[1], "tp3": tps[2], "risk_reward": "1 : 1.62~2.62"}
    else:
        sl = round(swing_high * 1.018, 8) if swing_high else round(current * 1.06, 8)
        if sl <= current:
            sl = round(current * 1.07, 8)
        risk = sl - current
        tps = [round(current - risk * r, 8) for r in (1.618, 2.0, 2.618)]
        return {"entry": round(current, 8), "sl": sl, "tp1": tps[0], "tp2": tps[1], "tp3": tps[2], "risk_reward": "1 : 1.62~2.62"}


def _format_price(p: float) -> str:
    if p >= 1000:
        return f"{p:,.2f}"
    elif p >= 1:
        return f"{p:,.4f}"
    else:
        return f"{p:.6f}"


def _round_rsi(rsi: Optional[float]) -> str:
    if rsi is None:
        return "N/A"
    return f"{float(rsi):.1f}"


def fetch_coingecko_simple(coin_id: str = "connex") -> Dict:
    """CONX용 간단 메타 (24h change 등). 실패 시 빈 dict."""
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}?vs_currency=usd&community_data=false&developer_data=false&sparkline=false"
    headers = {"User-Agent": "focused-elliott-analyzer/1.0"}
    try:
        import urllib.request
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        market = data.get("market_data", {})
        return {
            "price": market.get("current_price", {}).get("usd"),
            "change_24h": market.get("price_change_percentage_24h"),
            "vol_24h": market.get("total_volume", {}).get("usd"),
        }
    except Exception:
        return {}


def compute_overall_bias(adj_bull: int, adj_bear: int) -> Tuple[str, str]:
    """종합 바이어스 문구 + favored 방향 (long/short/neutral)."""
    if adj_bull >= 80 and adj_bull > adj_bear + 10:
        return "강력 롱 추천 (80점↑)", "long"
    if adj_bear >= 80 and adj_bear > adj_bull + 10:
        return "강력 숏 추천 (80점↑)", "short"
    if adj_bull >= 70 and adj_bull > adj_bear + 8:
        return "강한 롱 추천 (70점↑)", "long"
    if adj_bear >= 70 and adj_bear > adj_bull + 8:
        return "강한 숏 추천 (70점↑)", "short"
    if adj_bull >= 60 and adj_bull > adj_bear:
        return "상승 Setup 우위 (관찰)", "long"
    if adj_bear >= 60 and adj_bear > adj_bull:
        return "하락 Setup 우위 (관찰)", "short"
    return "양방향 혼조 또는 관망", "neutral"


def get_recommendation(score: int, is_bullish: bool) -> str:
    """
    직관적인 점수 기반 추천 문구.
    80점 이상 = 강력 추천 (사용자 요청 반영)
    """
    if score >= 80:
        stars = "★★★★★"
        action = "강력 롱 추천 🔥 (Wave 3 초기 고신뢰도, 적극 매수/롱 고려)" if is_bullish else "강력 숏 추천 🔥 (하락 Impulse 고신뢰도, 적극 매도/숏 고려)"
        return f"{stars} {action}"
    elif score >= 70:
        stars = "★★★★"
        action = "강한 롱 추천 (상승 Impulse 양호, 매수 검토)" if is_bullish else "강한 숏 추천 (하락 Impulse 양호, 숏 검토)"
        return f"{stars} {action}"
    elif score >= 60:
        stars = "★★★"
        action = "상승 Setup (관찰하며 진입 고려)" if is_bullish else "하락 Setup (관찰하며 숏 고려)"
        return f"{stars} {action}"
    elif score >= 50:
        stars = "★★"
        return f"{stars} 약한 {'상승' if is_bullish else '하락'} 신호 (위험 엄격 관리 필요, 소량 관찰)"
    else:
        return "★ 신호 미약 (관망 우세)"


# ============================================================
# 메인 분석 루프
# ============================================================
def run_focused_analysis(interval: str = "4h", lookback: int = 110, top_n: int = DEFAULT_TOP_N) -> List[Dict]:
    target_coins = get_top_volume_coins(top_n)
    print("=" * 64)
    print("엘리어트 파동 거래량 상위 종목 상승/하락 분석")
    print(f"대상: 바이낸스 USDT 24h 거래량 상위 {top_n}개")
    print(f"TF: {interval} (주요) + 1d (컨텍스트) | lookback ~{lookback}")
    print("=" * 64)

    if not target_coins:
        print("  [오류] 거래량 상위 종목을 가져오지 못했습니다.")
        return []

    try:
        tickers = get_24h_tickers()
        vol_map = {t["symbol"]: float(t.get("quoteVolume", 0)) for t in tickers}
        change_map = {t["symbol"]: float(t.get("priceChangePercent", 0)) for t in tickers}
    except Exception:
        vol_map, change_map = {}, {}

    print("  [선정 종목]")
    for c in target_coins:
        vol_m = c.get("volume_24h", vol_map.get(c["sym"], 0)) / 1_000_000
        print(f"    #{c['volume_rank']:2d} {c['sym']:<12} ${vol_m:.1f}M")

    results = []

    for coin in target_coins:
        kr, sym, eng = coin["kr"], coin["sym"], coin["name"]
        print(f"  [#{coin.get('volume_rank', '?')} {sym}] 분석 중...")

        candles = fetch_klines(sym, interval=interval, limit=lookback)
        if len(candles) < 30:
            print(f"    데이터 부족 - 스킵")
            continue

        daily = fetch_daily_context(sym)
        higher_bias = get_higher_tf_bias(daily) if daily else "일봉 데이터 부족"

        bull = analyze_elliott_bullish(candles)
        bear = analyze_elliott_bearish(candles)

        current = bull["price"]
        vol = vol_map.get(sym, 0) if sym in vol_map else 0
        chg = change_map.get(sym, 0) if sym in change_map else 0

        # 레벨 계산을 위한 최근 의미 swing 추출
        closes = [c["close"] for c in candles]
        swings = _find_recent_swings(closes, window=3, min_move_pct=0.012)
        recent_low = min(s["price"] for s in swings[-4:]) if swings else None
        recent_high = max(s["price"] for s in swings[-4:]) if swings else None

        long_levels = compute_levels(current, recent_low, recent_high, "long")
        short_levels = compute_levels(current, recent_low, recent_high, "short")

        # 직관적 점수 + 멀티 TF 보정
        bull_s = bull["score"]
        bear_s = bear["score"]

        mtf_bull_bonus = 6 if "상승 우위" in higher_bias else (0 if "하락 우위" in higher_bias else 0)
        mtf_bear_bonus = 6 if "하락 우위" in higher_bias else (0 if "상승 우위" in higher_bias else 0)

        adj_bull = min(100, bull_s + mtf_bull_bonus)
        adj_bear = min(100, bear_s + mtf_bear_bonus)

        bias, favored = compute_overall_bias(adj_bull, adj_bear)

        bull_reco = get_recommendation(adj_bull, True)
        bear_reco = get_recommendation(adj_bear, False)

        item = {
            "kr": kr,
            "symbol": sym,
            "eng": eng,
            "volume_rank": coin.get("volume_rank"),
            "current_price": current,
            "change_24h_pct": round(chg, 2),
            "volume_24h": vol,
            "rsi_4h": bull.get("rsi"),
            "higher_tf_bias": higher_bias,
            "bullish": bull,
            "bearish": bear,
            "bull_score": adj_bull,
            "bear_score": adj_bear,
            "bull_recommendation": bull_reco,
            "bear_recommendation": bear_reco,
            "overall_bias": bias,
            "favored": favored,
            "long_levels": long_levels,
            "short_levels": short_levels,
            "chart_candles": [
                {
                    "open_time": c["open_time"],
                    "open": c["open"],
                    "high": c["high"],
                    "low": c["low"],
                    "close": c["close"],
                }
                for c in candles
            ],
        }
        results.append(item)

    # =====================================================
    # 제일 위에 상승 신호 강한 애들 간략 요약 (사용자 요청)
    # =====================================================
    def _is_strong_long(r: Dict) -> bool:
        return "롱 추천" in r.get("overall_bias", "")

    def _is_strong_short(r: Dict) -> bool:
        return "숏 추천" in r.get("overall_bias", "")

    print("\n" + "=" * 64)
    print("📈 강한 롱 추천 종목 (70점↑, 상승 우위)")
    print("=" * 64)
    sorted_long = sorted(
        [r for r in results if _is_strong_long(r)],
        key=lambda x: x.get("bull_score", 0),
        reverse=True,
    )
    if sorted_long:
        for r in sorted_long:
            print(f"  • {r['kr']} ({r['symbol']}) : {r['bull_score']:3d}점  → {r['overall_bias']}")
    else:
        print("  현재 강한 롱 추천 조건에 해당하는 종목이 없습니다.")

    print("\n" + "=" * 64)
    print("📉 강한 숏 추천 종목 (70점↑, 하락 우위)")
    print("=" * 64)
    sorted_short = sorted(
        [r for r in results if _is_strong_short(r)],
        key=lambda x: x.get("bear_score", 0),
        reverse=True,
    )
    if sorted_short:
        for r in sorted_short:
            print(f"  • {r['kr']} ({r['symbol']}) : {r['bear_score']:3d}점  → {r['overall_bias']}")
    else:
        print("  현재 강한 숏 추천 조건에 해당하는 종목이 없습니다.")

    print("\n" + "=" * 64)
    print("📊 상승 신호 참고 (50점 이상, 점수 순)")
    print("=" * 64)
    sorted_bull = sorted(
        [r for r in results if r.get("bull_score", 0) >= 50],
        key=lambda x: x.get("bull_score", 0),
        reverse=True,
    )
    if sorted_bull:
        for r in sorted_bull:
            print(f"  • {r['kr']} ({r['symbol']}) : {r['bull_score']:3d}점  → {r.get('bull_recommendation', '')[:40]}")
    else:
        print("  현재 50점 이상의 뚜렷한 상승 신호가 없습니다.")

    print("=" * 64)
    print("아래는 종목별 상세 분석입니다.\n")

    # =====================================================
    # 원래 내용 (종목별 상세 출력)
    # =====================================================
    for r in results:
        current = r["current_price"]
        chg = r["change_24h_pct"]
        vol = r["volume_24h"]
        higher_bias = r["higher_tf_bias"]
        bull = r["bullish"]
        bear = r["bearish"]
        adj_bull = r["bull_score"]
        adj_bear = r["bear_score"]
        bull_reco = r.get("bull_recommendation", "")
        bear_reco = r.get("bear_recommendation", "")
        bias = r["overall_bias"]

        vol_str = f"${vol/1_000_000:.1f}M" if vol > 0 else ("N/A (CG)" if "CONX" in r["symbol"] else "N/A")
        print(f"\n[{r['kr']} / {r['eng']}] {r['symbol']}")
        print(f"  현재가: {_format_price(current)} | 24h: {chg:+.2f}% | Vol: {vol_str} | RSI4h: {_round_rsi(r['rsi_4h'])}")
        print(f"  일봉 컨텍스트: {higher_bias}")
        print(f"  📈 상승 신호 강도: {adj_bull:3d}/100  |  {bull_reco}")
        if bull["reasons"]:
            print(f"      이유: {' | '.join(bull['reasons'])}")
        print(f"  📉 하락 신호 강도: {adj_bear:3d}/100  |  {bear_reco}")
        if bear["reasons"]:
            print(f"      이유: {' | '.join(bear['reasons'])}")
        print(f"  → 종합: {bias}")

    return results


# ============================================================
# 리포트 저장 (txt + md + json)
# ============================================================
def save_reports(results: List[Dict], top_n: int = DEFAULT_TOP_N) -> Path:
    out_dir = Path(__file__).parent / "지정종목_엘리어트분석"
    out_dir.mkdir(exist_ok=True)

    now = datetime.now()
    ts = now.strftime("%Y%m%d_%H%M")
    base = out_dir / f"{ts}_지정종목_엘리어트_분석"

    # JSON (raw data)
    with open(f"{base}.json", "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": now.isoformat(),
            "pool": f"Binance USDT top {top_n} by 24h volume",
            "top_n": top_n,
            "coins": [r["symbol"] for r in results],
            "results": results
        }, f, ensure_ascii=False, indent=2)

    # TXT (기존 스타일)
    with open(f"{base}.txt", "w", encoding="utf-8") as f:
        f.write("# 엘리어트 파동 지정종목 상승/하락 분석 결과\n")
        f.write(f"# 생성: {now.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"# 대상: 바이낸스 USDT 24h 거래량 상위 {top_n}개\n")
        f.write("# TF: 4h 주분석 + 1d 컨텍스트 | 고전 Elliott 규칙 기반 (개선판)\n\n")

        # 상승 신호 강한 종목 간략 요약 (상단)
        sorted_bull = sorted(
            [r for r in results if r.get("bull_score", 0) >= 50],
            key=lambda x: x.get("bull_score", 0),
            reverse=True
        )
        f.write("## 📈 상승 신호 강한 종목 요약 (50점 이상)\n")
        if sorted_bull:
            for r in sorted_bull:
                score = r.get("bull_score", 0)
                reco = r.get("bull_recommendation", "")
                short = reco.split("—")[-1].strip() if "—" in reco else reco
                f.write(f"  • {r['kr']} ({r['symbol']}) : {score}점 → {short}\n")
        else:
            f.write("  현재 50점 이상 상승 신호 없음.\n")
        f.write("\n" + "="*60 + "\n\n")

        for r in results:
            f.write(f"\n{'='*60}\n")
            f.write(f"{r['kr']} ({r['eng']}) | {r['symbol']}\n")
            f.write(f"현재가: {_format_price(r['current_price'])} | 24h: {r['change_24h_pct']:+.2f}% | RSI: {_round_rsi(r['rsi_4h'])}\n")
            f.write(f"일봉: {r['higher_tf_bias']} | Vol: ${r['volume_24h']/1e6:.1f}M\n\n")

            bull_s = r.get('bull_score', r['bullish']['score'])
            bear_s = r.get('bear_score', r['bearish']['score'])
            f.write(f"📈 상승 신호 강도: {bull_s:3d}/100\n")
            f.write(f"   추천: {r.get('bull_recommendation', r['bullish']['label'])}\n")
            for reason in r['bullish']['reasons']:
                f.write(f"   - {reason}\n")
            f.write(f"   Long 레벨: Entry {_format_price(r['long_levels']['entry'])} | SL {_format_price(r['long_levels']['sl'])} | TP {_format_price(r['long_levels']['tp1'])} / {_format_price(r['long_levels']['tp2'])} / {_format_price(r['long_levels']['tp3'])}\n\n")

            f.write(f"📉 하락 신호 강도: {bear_s:3d}/100\n")
            f.write(f"   추천: {r.get('bear_recommendation', r['bearish']['label'])}\n")
            for reason in r['bearish']['reasons']:
                f.write(f"   - {reason}\n")
            f.write(f"   Short 레벨: Entry {_format_price(r['short_levels']['entry'])} | SL {_format_price(r['short_levels']['sl'])} | TP {_format_price(r['short_levels']['tp1'])} / {_format_price(r['short_levels']['tp2'])} / {_format_price(r['short_levels']['tp3'])}\n\n")

            f.write(f"→ 종합: {r['overall_bias']}\n")

    # MD (보기 좋게)
    with open(f"{base}.md", "w", encoding="utf-8") as f:
        f.write(f"# 엘리어트 파동 지정종목 분석 (상승/하락)\n\n")
        f.write(f"**생성일시**: {now.strftime('%Y-%m-%d %H:%M:%S')}  \n")
        f.write(f"**대상**: 바이낸스 USDT 24h 거래량 상위 {top_n}개  \n")
        f.write("**방법**: 4h 중심 + 일봉 컨텍스트, 고전 Elliott Impulse 규칙 (Wave2 피보나치, Wave3 not shortest, impulse 강도 등)  \n\n")
        f.write("> **면책**: 참고용 도구. 실제 매매는 본인 책임 + 상위 TF 확인 + 리스크 관리.\n\n")

        # =====================================================
        # 제일 위: 상승 신호 강한 종목 간략 정리 (사용자 요청)
        # =====================================================
        sorted_bull = sorted(
            [r for r in results if r.get("bull_score", 0) >= 50],
            key=lambda x: x.get("bull_score", 0),
            reverse=True
        )

        f.write("## 📈 상승 신호 강한 종목 요약 (50점 이상, 점수 높은 순)\n\n")
        if sorted_bull:
            for r in sorted_bull:
                score = r.get("bull_score", 0)
                reco = r.get("bull_recommendation", "")
                short = reco.split("—")[-1].strip() if "—" in reco else reco
                f.write(f"- **{r['kr']}** ({r['symbol']}) — **{score}점** → {short}\n")
        else:
            f.write("- 현재 50점 이상의 뚜렷한 상승 신호가 없습니다.\n")
        f.write("\n---\n\n")

        # 요약 테이블 (더 직관적으로)
        f.write("## 종합 요약\n\n")
        f.write("| 종목 | 현재가 | 24h% | RSI | 상승점수 | 하락점수 | 종합 추천 |\n")
        f.write("|------|--------|------|-----|----------|----------|-----------|\n")
        for r in results:
            rsi_str = _round_rsi(r['rsi_4h'])
            bull_s = r.get('bull_score', r['bullish']['score'])
            bear_s = r.get('bear_score', r['bearish']['score'])
            bias = r['overall_bias']
            f.write(f"| {r['kr']} | {_format_price(r['current_price'])} | {r['change_24h_pct']:+.1f}% | {rsi_str} | **{bull_s}** | {bear_s} | {bias} |\n")
        f.write("\n> **해석 가이드**: 80점↑ = 강력 롱/숏 추천. 70점↑ = 강한 롱/숏 추천. 60점대 = Setup 관찰.\n\n")

        for r in results:
            bull_s = r.get('bull_score', r['bullish']['score'])
            bear_s = r.get('bear_score', r['bearish']['score'])
            bull_reco = r.get('bull_recommendation', '')
            bear_reco = r.get('bear_recommendation', '')

            f.write(f"## {r['kr']} ({r['eng']}) - {r['symbol']}\n\n")
            f.write(f"- **현재가**: {_format_price(r['current_price'])} (24h {r['change_24h_pct']:+.2f}%)  \n")
            f.write(f"- **RSI (4h)**: {_round_rsi(r['rsi_4h'])}   | **Vol**: ${r['volume_24h']/1_000_000:.1f}M  \n")
            f.write(f"- **일봉 컨텍스트**: {r['higher_tf_bias']}\n\n")

            f.write(f"### 📈 상승 분석 — **{bull_s}점**\n")
            f.write(f"**추천: {bull_reco}**\n\n")
            for reason in r['bullish']['reasons']:
                f.write(f"- {reason}\n")
            f.write("\n**Long 레벨 (참고)**\n")
            ll = r['long_levels']
            f.write(f"- Entry: `{_format_price(ll['entry'])}` | SL: `{_format_price(ll['sl'])}` | RR: {ll['risk_reward']}\n")
            f.write(f"- TP1 (1.618): `{_format_price(ll['tp1'])}` | TP2 (2.0): `{_format_price(ll['tp2'])}` | TP3 (2.618): `{_format_price(ll['tp3'])}`\n\n")

            f.write(f"### 📉 하락 분석 — **{bear_s}점**\n")
            f.write(f"**추천: {bear_reco}**\n\n")
            for reason in r['bearish']['reasons']:
                f.write(f"- {reason}\n")
            f.write("\n**Short 레벨 (참고)**\n")
            sl = r['short_levels']
            f.write(f"- Entry: `{_format_price(sl['entry'])}` | SL: `{_format_price(sl['sl'])}` | RR: {sl['risk_reward']}\n")
            f.write(f"- TP1 (1.618): `{_format_price(sl['tp1'])}` | TP2 (2.0): `{_format_price(sl['tp2'])}` | TP3 (2.618): `{_format_price(sl['tp3'])}`\n\n")

            f.write(f"**→ 종합 의견**: {r['overall_bias']}\n\n")
            f.write("---\n\n")

    print(f"\n✅ 리포트 저장 완료:")
    print(f"   {base}.md")
    print(f"   {base}.txt")
    print(f"   {base}.json")
    return base


# ============================================================
# 실행부
# ============================================================
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="엘리어트 지정종목 상승/하락 분석")
    parser.add_argument("--interval", default="4h", help="기본 분석 TF (기본 4h)")
    parser.add_argument("--lookback", type=int, default=110, help="캔들 수")
    parser.add_argument("--top", type=int, default=DEFAULT_TOP_N, help="거래량 상위 N개 (기본 20)")
    args = parser.parse_args()

    results = run_focused_analysis(interval=args.interval, lookback=args.lookback, top_n=args.top)

    if results:
        save_reports(results, top_n=args.top)
        print("\n완료. 리포트 파일을 확인하세요.")
    else:
        print("분석 결과가 없습니다.")

    print("\n(팁) python 엘리어트_지정종목_분석.py --interval 1h --lookback 80 로 단기 분석도 가능")