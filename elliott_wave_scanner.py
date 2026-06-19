#!/usr/bin/env python3
"""
Elliott Wave Scanner
Scans top 100 highest volume USDT pairs on Binance 4h timeframe
for potential bullish Elliott Wave impulse setups (Wave 3 candidates).

Designed to run in GitHub Actions and output clean JSON + Markdown
for a public website.
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict
import urllib.request

BASE_URL = "https://api.binance.com"


def _fetch_json(url: str, max_retries: int = 3) -> dict:
    headers = {"User-Agent": "elliott-wave-scanner/1.0"}
    last_err = None
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            last_err = e
            time.sleep(1.2 * (attempt + 1))
    raise RuntimeError(f"Binance API failed: {url} - {last_err}")


def get_24h_tickers() -> List[Dict]:
    return _fetch_json(f"{BASE_URL}/api/v3/ticker/24hr")


def get_klines(symbol: str, interval: str = "4h", limit: int = 85) -> List[Dict]:
    url = f"{BASE_URL}/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    raw = _fetch_json(url)
    candles = []
    for row in raw:
        candles.append({
            "open_time": int(row[0]),
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[5]),
        })
    return candles


def calculate_rsi(closes: List[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0))
        losses.append(max(-delta, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _find_recent_swings(closes: List[float], window: int = 3, min_move_pct: float = 0.009) -> List[Dict]:
    raw = []
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

    filtered = []
    for s in raw:
        if not filtered or abs(s["price"] - filtered[-1]["price"]) / filtered[-1]["price"] >= min_move_pct:
            filtered.append(s)
    return filtered


def analyze_elliott(candles: List[Dict]) -> Dict:
    """
    진짜 이론적 Elliott Wave 관점으로 최대한 정확하게 재설계.
    Classic Elliott Impulse Rules (Bullish Wave 3 focus):
    - 5-wave structure.
    - Wave 2: 38.2~78.6% retrace of Wave 1 (never >100%).
    - Wave 3: never the shortest, usually longest/strongest, starts with break of Wave 1 high.
    - No overlap (Wave 4 shouldn't overlap Wave 1).
    - Momentum: strong extension on Wave 3, often with volume.
    - This version identifies potential Wave1 -> valid Wave2 -> breakout above Wave1 high as Wave3 start.
    Score based on rule compliance (higher = more rules followed).
    """
    if len(candles) < 40:
        return {"score": 0, "wave": "데이터 부족", "reasons": ["40개 이상 캔들 필요"], "bullish": False}

    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    vols = [c.get("volume", 0) for c in candles]
    current_price = closes[-1]
    rsi = calculate_rsi(closes, 14)

    # Significant swings (larger window for "theoretical" pivots, not micro noise)
    swings = _find_recent_swings(closes, window=4, min_move_pct=0.012)
    score = 5
    reasons = []
    label = "불명확 / 조정 또는 다른 구조"

    if len(swings) < 4:
        return {"score": 25, "wave": label, "reasons": ["의미 있는 스윙 부족 (이론적 Wave 구조 확인 불가)"], "bullish": False, "rsi": rsi, "price": round(current_price, 6)}

    recent = swings[-7:] if len(swings) >= 7 else swings

    # 1. Find most recent clear "up leg" as potential Wave 1
    wave1_high = None
    wave1_low = None
    wave1_size = 0
    for i in range(len(recent) - 1, 0, -1):
        if recent[i]["type"] == "high" and recent[i-1]["type"] == "low":
            wave1_high = recent[i]["price"]
            wave1_low = recent[i-1]["price"]
            wave1_size = wave1_high - wave1_low
            break

    if wave1_size <= 0:
        return {"score": 20, "wave": label, "reasons": ["명확한 Wave 1 후보 leg 없음"], "bullish": False, "rsi": rsi, "price": round(current_price, 6)}

    # 2. Find the pullback after that high as potential Wave 2
    wave2_retr = 0.0
    wave2_low = None
    wave2_high = None
    for i in range(len(recent)):
        if recent[i]["type"] == "high" and abs(recent[i]["price"] - wave1_high) / wave1_high < 0.03:
            # found the Wave1 high
            if i + 1 < len(recent) and recent[i+1]["type"] == "low":
                wave2_high = recent[i]["price"]
                wave2_low = recent[i+1]["price"]
                wave2_retr = (wave2_high - wave2_low) / wave1_size
            break

    # 3. Check for breakout above Wave 1 high (Wave 3 start signal)
    breakout = current_price > wave1_high * 1.003  # small buffer for real trading

    # === Theory-based scoring ===
    # Base for having the 1-2 structure
    score = 10

    # Wave 2 retracement quality (core rule)
    if 0.382 <= wave2_retr <= 0.786:
        score += 22
        reasons.append(f"유효 Wave 2 조정 {wave2_retr*100:.1f}% (38.2-78.6% 규칙 준수)")
        if 0.50 <= wave2_retr <= 0.618:
            score += 6
            reasons.append("이상적 50-61.8% 조정 ( alternation & Fib 우수)")
    elif wave2_retr < 0.382:
        score += 8
        reasons.append(f"얕은 조정 {wave2_retr*100:.1f}% (가능하지만 Wave 3 약할 수 있음)")
    else:
        score -= 10
        reasons.append(f"과도 조정 {wave2_retr*100:.1f}% (Wave 2 규칙 위반 위험 높음)")

    # Breakout above Wave 1 (the trigger for Wave 3)
    if breakout:
        score += 26
        reasons.append("Wave 1 고점 돌파 확인 (Wave 3 impulse 시작 신호)")
        label = "Wave 3 진행 또는 시작"
        # Strength of breakout
        break_pct = (current_price - wave1_high) / wave1_high
        if break_pct > 0.015:
            score += 5
            reasons.append("강한 돌파 (>1.5%)")
    else:
        score -= 12
        reasons.append("아직 Wave 1 고점 미돌파 (Wave 3 미시작)")

    # Momentum on the presumed Wave 3 leg (theory: Wave 3 is powerful)
    if wave2_low:
        leg3_size = current_price - wave2_low
        extension_ratio = leg3_size / wave1_size if wave1_size > 0 else 0
        if extension_ratio > 1.0:
            score += 8
            reasons.append(f"Wave 3 leg이 Wave 1보다 강함 (이론적 강세)")
        if extension_ratio < 0.6:
            score -= 5

    # Volume & candle confirmation on current move (impulse characteristic)
    if len(vols) >= 8:
        recent_vol = sum(vols[-3:]) / 3
        prev_vol = sum(vols[-8:-3]) / 5
        if prev_vol > 0 and recent_vol > prev_vol * 1.3:
            score += 7
            reasons.append("Wave 3 구간 거래량 강한 증가 (impulse 동반)")

    # RSI health (Wave 3 usually starts from healthy or oversold, not extreme overbought)
    if rsi is not None:
        if 43 <= rsi <= 68:
            score += 7
            reasons.append(f"RSI {rsi:.0f} (양호한 impulse 시작 구간)")
        elif rsi < 40:
            score += 5
            reasons.append(f"RSI {rsi:.0f} (과매도 반등 후보)")
        elif rsi > 78:
            score -= 9
            reasons.append(f"RSI {rsi:.0f} (과매수 - Wave 3 시작 부적합)")

    # Over-extension penalty (if already run a lot from Wave 2 low, it may be Wave 5 or extended Wave 3, not the "start")
    if wave2_low:
        run_from_w2 = (current_price - wave2_low) / wave1_size if wave1_size > 0 else 0
        if run_from_w2 > 1.6:
            score -= 8
            reasons.append(f"Wave 2 저점 대비 이미 {run_from_w2:.1f}x 연장 (시작 시점 아님)")

    score = max(5, min(100, int(score)))

    if score >= 70:
        if "Wave 3" not in label:
            label = "High Conviction Wave 3 Impulse (이론 규칙 강하게 충족)"
        bullish = True
    elif score >= 58:
        label = "Wave 3 Setup (추가 확인 필요)"
        bullish = True
    else:
        bullish = False

    # Useful meta for the UI
    meta = {
        "wave1_size_pct": round(wave1_size / wave1_low * 100, 1) if wave1_low else 0,
        "wave2_retr_pct": round(wave2_retr * 100, 1) if wave2_retr else 0,
        "breakout_from_w1_high_pct": round((current_price - wave1_high) / wave1_high * 100, 1) if wave1_high else 0
    }

    return {
        "score": score,
        "wave": label,
        "reasons": reasons[:4],
        "bullish": bullish,
        "rsi": rsi,
        "price": round(current_price, 6),
        "meta": meta
    }


def find_candidates(top_n: int = 10) -> List[Dict]:
    print("[Scan] Fetching 24h tickers...")
    tickers = get_24h_tickers()

    usdt_pairs = []
    for t in tickers:
        if t["symbol"].endswith("USDT"):
            try:
                vol = float(t.get("quoteVolume", 0))
                usdt_pairs.append((t["symbol"], vol))
            except:
                pass

    usdt_pairs.sort(key=lambda x: x[1], reverse=True)
    scan_list = [sym for sym, _ in usdt_pairs[:100]]  # Strictly top 100 by volume

    print(f"[Scan] Scanning top {len(scan_list)} high-volume USDT pairs...")

    results = []
    for i, sym in enumerate(scan_list, 1):
        try:
            candles = get_klines(sym, "4h", 85)
            if len(candles) < 35:
                continue
            analysis = analyze_elliott(candles)
            if not analysis["bullish"]:
                continue

            vol = next((v for s, v in usdt_pairs if s == sym), 0)

            item = {
                "symbol": sym,
                "score": analysis["score"],   # 제일 처음 버전 그대로 (boost 없음)
                "wave": analysis["wave"],
                "reasons": analysis["reasons"],
                "price": analysis["price"],
                "volume_24h": vol,
                "rsi": analysis.get("rsi"),
                "entry": analysis["price"],
                "tp": round(analysis["price"] + (analysis["price"] - min(c["low"] for c in candles[-25:]) * 0.983) * 1.272, 8),
                "sl": round(min(c["low"] for c in candles[-25:]) * 0.983, 8),
                "meta": analysis.get("meta", {})
            }
            results.append(item)

            if i % 15 == 0:
                print(f"  ... processed {i}/{len(scan_list)}")
            time.sleep(0.1)
        except Exception as e:
            time.sleep(0.05)
            continue

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_n]


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="results")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    results = find_candidates(top_n=10)

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)

    # latest.json for website
    data = {
        "generated_at": now.isoformat(),
        "candidates": results,
        "meta": {"pool": "Top 100 USDT by 24h volume"}
    }
    with open(out / "latest.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    # latest.md
    with open(out / "latest.md", "w", encoding="utf-8") as f:
        f.write(f"# Elliott Wave Scanner - Latest Results\n\n")
        f.write(f"**Time**: {now.strftime('%Y-%m-%d %H:%M UTC')}\n")
        f.write(f"**Pool**: Top 100 highest volume USDT pairs\n\n")
        if not results:
            f.write("No candidates met the criteria this run.\n")
        else:
            for i, c in enumerate(results, 1):
                v = f"${c['volume_24h']/1e6:.1f}M"
                f.write(f"### {i}. {c['symbol']} — Score {c['score']}\n")
                f.write(f"- Price: {c['price']} | Vol: {v} | RSI: {c['rsi']}\n")
                f.write(f"- Assessment: {c['wave']}\n")
                f.write(f"- Reasons: {' | '.join(c['reasons'])}\n")
                f.write(f"- Suggested: Entry {c['entry']} | TP {c['tp']} | SL {c['sl']}\n\n")

    print(f"\n✅ Saved results to {out}/latest.json and latest.md")


if __name__ == "__main__":
    main()