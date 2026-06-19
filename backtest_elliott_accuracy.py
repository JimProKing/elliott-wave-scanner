"""
Elliott Wave Scanner Accuracy Backtest (Historical 4h charts)
- Replays _analyze_elliott_structure on past slices of 4h data.
- Measures forward performance after high-score signals.
- Uses public Binance klines (no keys needed).
"""

import urllib.request
import json
import time
from datetime import datetime, timezone
from typing import List, Dict

BASE = "https://api.binance.com"

# ---------- Data fetch ----------
def fetch_klines_historical(symbol: str, interval: str = "4h", limit: int = 1000,
                            start_ms: int = None, end_ms: int = None) -> List[Dict]:
    url = f"{BASE}/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    if start_ms:
        url += f"&startTime={start_ms}"
    if end_ms:
        url += f"&endTime={end_ms}"
    headers = {"User-Agent": "python-trading-utils/1.0"}
    last_err = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
                out = []
                for r in raw:
                    out.append({
                        "open_time": int(r[0]),
                        "open": float(r[1]),
                        "high": float(r[2]),
                        "low": float(r[3]),
                        "close": float(r[4]),
                        "volume": float(r[5]),
                    })
                return out
        except Exception as e:
            last_err = e
            time.sleep(0.7 * (attempt + 1))
    raise RuntimeError(f"Binance klines fetch failed for {symbol}: {last_err}")


def fetch_long_history(symbol: str, interval: str = "4h", bars: int = 400) -> List[Dict]:
    """Fetch up to 'bars' most recent candles (works by chaining if >1000 needed, but 4h 400 is fine in one call)."""
    data = fetch_klines_historical(symbol, interval, limit=min(1000, bars))
    # If we want older, we could loop backward using first open_time, but for 4h ~ 400 bars (~67 days) one call is sufficient.
    return data


# ---------- Exact copy of scanner logic (for faithful replay) ----------
def calculate_rsi(closes: List[float], period: int = 14):
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(delta if delta > 0 else 0.0)
        losses.append(-delta if delta < 0 else 0.0)
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _find_recent_swings(closes: List[float], window: int = 3, min_move_pct: float = 0.012) -> List[Dict]:
    """
    개선된 스윗 탐지 (scanner와 동일):
    - window=3 + min 1.4% 이동 필터 → 노이즈 제거, 의미 있는 구조만
    """
    raw_swings: List[Dict] = []
    n = len(closes)
    for i in range(window, n - window):
        is_high = all(closes[i] > closes[i - k] for k in range(1, window + 1)) and \
                  all(closes[i] > closes[i + k] for k in range(1, window + 1))
        is_low = all(closes[i] < closes[i - k] for k in range(1, window + 1)) and \
                 all(closes[i] < closes[i + k] for k in range(1, window + 1))
        if is_high:
            raw_swings.append({"idx": i, "price": closes[i], "type": "high"})
        elif is_low:
            raw_swings.append({"idx": i, "price": closes[i], "type": "low"})

    filtered: List[Dict] = []
    for s in raw_swings:
        if not filtered:
            filtered.append(s)
            continue
        prev_price = filtered[-1]["price"]
        move = abs(s["price"] - prev_price) / prev_price if prev_price > 0 else 0
        if move >= min_move_pct:
            filtered.append(s)
    return filtered


def _analyze_elliott_structure(candles: List[Dict]) -> Dict:
    """ 개선된 버전 (scanner.py와 동기화). 과거 데이터로 정확도 측정용. """
    if len(candles) < 35:
        return {"score": 0, "estimated_wave": "데이터 부족", "reasons": ["캔들 부족 (최소 35 필요)"], "bullish": False}

    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    opens = [c.get("open", c["close"]) for c in candles]
    vols = [c.get("volume", 0) for c in candles]
    current_price = closes[-1]
    rsi = calculate_rsi(closes, 14)

    swings = _find_recent_swings(closes, window=3, min_move_pct=0.014)
    score = 14
    reasons: List[str] = []
    wave_label = "불명확 / 조정 중"

    if len(swings) < 3:
        score += 3
        reasons.append("의미 있는 스윗 포인트 부족 (노이즈 필터 적용)")
        return {"score": min(38, score), "estimated_wave": wave_label, "reasons": reasons[:3],
                "bullish": False, "rsi": rsi, "current_price": round(current_price, 6)}

    recent = swings[-6:] if len(swings) >= 6 else swings

    # HH / HL (더 엄격)
    hh_hl_points = 0
    last_high = None
    last_low = None
    for s in recent:
        if s["type"] == "high":
            if last_high is None or s["price"] > last_high:
                hh_hl_points += 1
            last_high = s["price"]
        else:
            if last_low is None or s["price"] > last_low:
                hh_hl_points += 1
            last_low = s["price"]

    if hh_hl_points >= 5:
        score += 18
        reasons.append("Higher High + Higher Low 강한 연속 구조 (청정 스윗)")
    elif hh_hl_points >= 4:
        score += 12
        reasons.append("Higher High + Higher Low 양호한 구조")

    # Retrace
    max_retrace = 0.0
    valid_retrace_leg = False
    for i in range(2, len(recent)):
        p2 = recent[i - 2]
        p1 = recent[i - 1]
        p0 = recent[i]
        if p1["type"] == "high" and p0["type"] == "low":
            leg_up = p1["price"] - p2["price"]
            leg_down = p1["price"] - p0["price"]
            if leg_up > 0:
                retr = leg_down / leg_up
                if retr > max_retrace:
                    max_retrace = retr
                valid_retrace_leg = True

    if 0.382 <= max_retrace <= 0.786:
        score += 16
        reasons.append(f"주요 조정 {max_retrace*100:.1f}% (피보나치 38.2~78.6% 존)")
    elif 0.25 <= max_retrace < 0.382:
        score += 8
        reasons.append(f"얏은 조정 후 반등 (가능한 Wave 3/5)")
    elif max_retrace > 0.82 and valid_retrace_leg:
        score -= 5

    # 핵심: 개선된 breakout (1.5% + 강도/거래량)
    last_significant_high = None
    for s in reversed(recent):
        if s["type"] == "high":
            last_significant_high = s["price"]
            break

    breakout_ok = False
    if last_significant_high and current_price > last_significant_high * 1.012:
        last_c = candles[-1]
        body = last_c["close"] - last_c["open"]
        candle_range = last_c["high"] - last_c["low"]
        strong_bullish_candle = body > 0 and candle_range > 0 and (body / candle_range) >= 0.45

        vol_thrust = False
        if len(vols) >= 20:
            recent_v = sum(vols[-4:]) / 4.0
            prev_v = sum(vols[-16:-4]) / 12.0 if len(vols) > 16 else recent_v
            if prev_v > 0 and recent_v > prev_v * 1.22:
                vol_thrust = True

        if strong_bullish_candle or vol_thrust:
            breakout_ok = True
            score += 24
            reasons.append("조정 후 의미 있는 고점 돌파 + impulse 확인 (Wave 3 후보)")
            wave_label = "Wave 3 진행 또는 시작"
        else:
            score += 9
            reasons.append("고점 돌파 관찰 (강도 미흉)")

    # 최근 impulse 강도 (가속)
    if len(closes) >= 16:
        recent_up = (current_price - closes[-8]) / closes[-8] if closes[-8] else 0
        prev_up = (closes[-8] - closes[-16]) / closes[-16] if closes[-16] else 0
        if recent_up > 0.09 and recent_up > prev_up * 0.6:
            score += 8
            reasons.append("최근 상승 가속 / 강한 impulse")
        elif recent_up > 0.055:
            score += 4

    # RSI (과매수 페널티)
    if rsi is not None:
        if 42 <= rsi <= 66:
            score += 8
            reasons.append(f"RSI {rsi:.0f} (상승 모멘텀 양호)")
        elif rsi < 37:
            score += 10
            reasons.append(f"RSI {rsi:.0f} (과매도 후 반등 후보)")
        elif rsi > 76:
            score -= 7
            reasons.append(f"RSI {rsi:.0f} (과매수 주의 — impulse 신뢰도 하락)")

    # SMA (조금 엄격)
    if len(closes) >= 20:
        sma20 = sum(closes[-20:]) / 20
        if current_price > sma20 * 1.008:
            score += 5
            reasons.append("가격 SMA20 상회 (추세 지지)")
        elif current_price < sma20 * 0.995:
            score -= 7

    # 강한 상승 캔들 카운트
    strong_up_candles = 0
    for i in range(max(0, len(candles)-5), len(candles)):
        c = candles[i]
        if c["close"] > c["open"] and (c["close"] - c["open"]) > 0.35 * (c["high"] - c["low"]):
            strong_up_candles += 1
    if strong_up_candles >= 3:
        score += 4
        reasons.append(f"최근 강한 상승 캔들 {strong_up_candles}개")

    score = max(5, min(100, int(score)))

    if score >= 70:
        if "Wave 3" not in wave_label:
            wave_label = "상승 impulse 강세 (Wave 3 가능성 높음)"
        bullish = True
    elif score >= 55:
        wave_label = "상승 전환 / 초기 impulse (필터 통과)"
        bullish = True
    else:
        bullish = False

    return {
        "score": score,
        "estimated_wave": wave_label,
        "reasons": reasons[:4],
        "bullish": bullish,
        "rsi": rsi,
        "current_price": round(current_price, 6),
    }


# ---------- Backtest engine (TP/SL도 scanner 개선 버전과 동기화) ----------
def run_backtest_on_history(symbol: str, history: List[Dict], lookback: int = 85,
                            min_score: int = 68, forward_bars_list: List[int] = (8, 16, 24)):
    """
    history: list of candles oldest -> newest.
    For each possible 'now' = i (i >= lookback + some margin), pretend we are at history[i-1] close.
    Run analysis on history[i-lookback : i].
    Record signal, then look forward_bars into future for performance.
    """
    n = len(history)
    if n < lookback + 30:
        return {"symbol": symbol, "error": "insufficient history"}

    signals = []
    for i in range(lookback + 10, n - max(forward_bars_list) - 1):
        past_slice = history[i - lookback : i]   # up to but not including future
        analysis = _analyze_elliott_structure(past_slice)
        if not analysis.get("bullish") or analysis["score"] < min_score:
            continue

        entry_time = history[i-1]["open_time"]
        entry_price = analysis["current_price"]  # or history[i-1]["close"]

        # Forward performance
        fwd = {}
        for fb in forward_bars_list:
            if i + fb >= n:
                continue
            future_closes = [history[j]["close"] for j in range(i, i + fb + 1)]
            future_highs = [history[j]["high"] for j in range(i, i + fb + 1)]
            future_lows = [history[j]["low"] for j in range(i, i + fb + 1)]

            max_up = (max(future_highs) - entry_price) / entry_price * 100
            min_down = (min(future_lows) - entry_price) / entry_price * 100
            end_price = history[i + fb]["close"]
            end_move = (end_price - entry_price) / entry_price * 100

            fwd[fb] = {
                "max_up_pct": round(max_up, 2),
                "min_down_pct": round(min_down, 2),
                "end_move_pct": round(end_move, 2),
                "hit_3pct_up": max_up >= 3.0,
                "hit_6pct_up": max_up >= 6.0,
            }

        signals.append({
            "idx": i,
            "time": datetime.fromtimestamp(entry_time / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M"),
            "score": analysis["score"],
            "label": analysis["estimated_wave"],
            "entry": entry_price,
            "rsi": analysis.get("rsi"),
            "forward": fwd,
        })

    # Aggregate stats
    total = len(signals)
    if total == 0:
        return {"symbol": symbol, "signals": 0}

    stats = {}
    for fb in forward_bars_list:
        ups = [s["forward"][fb]["max_up_pct"] for s in signals if fb in s["forward"]]
        ends = [s["forward"][fb]["end_move_pct"] for s in signals if fb in s["forward"]]
        hit3 = sum(1 for s in signals if fb in s["forward"] and s["forward"][fb]["hit_3pct_up"])
        hit6 = sum(1 for s in signals if fb in s["forward"] and s["forward"][fb]["hit_6pct_up"])
        stats[fb] = {
            "count": len(ups),
            "avg_max_up": round(sum(ups)/len(ups), 2) if ups else 0,
            "avg_end": round(sum(ends)/len(ends), 2) if ends else 0,
            "median_max_up": round(sorted(ups)[len(ups)//2], 2) if ups else 0,
            "hit_3pct_rate": round(hit3 / len(ups) * 100, 1) if ups else 0,
            "hit_6pct_rate": round(hit6 / len(ups) * 100, 1) if ups else 0,
        }

    return {
        "symbol": symbol,
        "signals": total,
        "signal_details": signals[-6:],  # last few for inspection
        "stats": stats,
    }


def main():
    print("=== Elliott Wave Scanner Historical Accuracy Backtest ===\n")
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"]
    interval = "4h"
    lookback = 85
    min_score_strong = 68
    min_score_any_bullish = 52
    fwd_windows = [8, 16, 24]  # ~1.3d, 2.7d, 4d on 4h

    for sym in symbols:
        print(f"\n--- {sym} ---")
        try:
            hist = fetch_long_history(sym, interval, bars=420)
            print(f"  Loaded {len(hist)} bars (~{len(hist)*4/24:.1f} days)")

            res_strong = run_backtest_on_history(sym, hist, lookback, min_score_strong, fwd_windows)
            res_mild = run_backtest_on_history(sym, hist, lookback, min_score_any_bullish, fwd_windows)

            print(f"  Strong signals (score>={min_score_strong}): {res_strong.get('signals', 0)}")
            if res_strong.get('signals', 0) > 0:
                for fb, st in res_strong["stats"].items():
                    print(f"    +{fb}bars (~{fb*4}h): avg_max_up={st['avg_max_up']}% | hit>=3% {st['hit_3pct_rate']}% | hit>=6% {st['hit_6pct_rate']}% | avg_end_move={st['avg_end']}%")

            print(f"  Any bullish (score>={min_score_any_bullish}): {res_mild.get('signals', 0)}")
            if res_mild.get('signals', 0) > 0:
                for fb, st in res_mild["stats"].items():
                    print(f"    +{fb}bars: avg_max_up={st['avg_max_up']}% | hit>=3% {st['hit_3pct_rate']}% | hit>=6% {st['hit_6pct_rate']}%")
        except Exception as e:
            print(f"  ERROR for {sym}: {e}")
        time.sleep(0.4)

    print("\n=== Backtest complete ===")


if __name__ == "__main__":
    main()