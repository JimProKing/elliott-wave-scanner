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
    if len(candles) < 35:
        return {"score": 0, "wave": "Insufficient data", "reasons": ["Too few candles"], "bullish": False}

    closes = [c["close"] for c in candles]
    vols = [c.get("volume", 0) for c in candles]
    current = closes[-1]
    rsi = calculate_rsi(closes, 14)

    swings = _find_recent_swings(closes, window=3, min_move_pct=0.009)
    score = 12
    reasons = []
    label = "Unclear / Consolidation"

    if len(swings) < 3:
        return {"score": 35, "wave": label, "reasons": ["Not enough swings"], "bullish": False, "rsi": rsi, "price": round(current, 6)}

    recent = swings[-6:] if len(swings) >= 6 else swings

    # HH/HL
    hh = 0
    last_high = None
    last_high_idx = None
    last_low = None
    for s in recent:
        if s["type"] == "high":
            if last_high is None or s["price"] > last_high:
                hh += 1
            last_high = s["price"]
            last_high_idx = s["idx"]
        else:
            if last_low is None or s["price"] > last_low:
                hh += 1
            last_low = s["price"]

    if hh >= 4:
        score += 14
        reasons.append("Strong HH + HL structure")
    elif hh >= 3:
        score += 8
        reasons.append("Good HH + HL structure")

    # Best recent retrace (Wave 2 like)
    best_retr = 0.0
    retr_low = None
    for i in range(1, len(recent)):
        if recent[i-1]["type"] == "high" and recent[i]["type"] == "low":
            prev = recent[i-2]["price"] if i >= 2 else recent[i-1]["price"] * 0.92
            leg_up = recent[i-1]["price"] - prev
            leg_dn = recent[i-1]["price"] - recent[i]["price"]
            if leg_up > 0:
                r = leg_dn / leg_up
                if 0.30 <= r <= 0.80 and r > best_retr:
                    best_retr = r
                    retr_low = recent[i]["price"]

    if 0.38 <= best_retr <= 0.78:
        score += 17
        reasons.append(f"Good Wave 2-style retrace {best_retr*100:.1f}%")
    elif 0.25 <= best_retr < 0.38:
        score += 7
        reasons.append(f"Adjust {best_retr*100:.1f}%")
    elif best_retr > 0.82:
        score -= 4

    # Fresh breakout
    if last_high and current > last_high * 1.004:
        age = len(closes) - 1 - last_high_idx if last_high_idx is not None else 99
        if age <= 5:
            score += 23
        elif age <= 10:
            score += 17
        else:
            score += 9
        label = "Wave 3 in progress / starting"
        reasons.append(f"Break of prior high (age={age} bars)")

        last = candles[-1]
        body_r = (last["close"] - last["open"]) / max(0.0001, last["high"] - last["low"])
        if body_r >= 0.38:
            score += 6
            reasons.append("Strong breakout candle")

        if len(vols) >= 8:
            avg = sum(vols[-8:-2]) / 6
            rec = sum(vols[-2:]) / 2
            if avg > 0 and rec > avg * 1.2:
                score += 5
                reasons.append("Volume surge on impulse")

    # Extension penalty
    if retr_low:
        leg = (current - retr_low) / retr_low
        if leg > 0.30:
            score -= 9
            reasons.append(f"Extended move +{leg*100:.0f}%")
        elif leg > 0.20:
            score -= 3

    # Recent strength
    if len(closes) >= 12:
        move = (current - closes[-7]) / closes[-7]
        if move > 0.07:
            score += 6
            reasons.append("Recent acceleration")

    # RSI
    if rsi is not None:
        if 46 <= rsi <= 69:
            score += 6
            reasons.append(f"RSI {rsi:.0f} healthy")
        elif rsi < 40:
            score += 5
        elif rsi > 81:
            score -= 5
            reasons.append(f"RSI {rsi:.0f} overbought")

    # Basic trend
    if len(closes) >= 18:
        sma = sum(closes[-18:]) / 18
        if current > sma:
            score += 3

    # Strong impulse candles
    strong_candles = 0
    for i in range(max(0, len(candles)-5), len(candles)):
        c = candles[i]
        if c["close"] > c["open"] and (c["close"] - c["open"]) > 0.35 * (c["high"] - c["low"]):
            strong_candles += 1
    if strong_candles >= 2:
        score += 4

    score = max(5, min(100, int(score)))

    if score >= 64:
        if "Wave 3" not in label:
            label = "High Conviction Impulse"
        bullish = True
    elif score >= 51:
        label = "Impulse Setup"
        bullish = True
    else:
        bullish = False

    meta = {}
    if retr_low:
        meta["leg_pct"] = round((current - retr_low) / retr_low * 100, 1)
    if last_high_idx is not None:
        meta["breakout_age_bars"] = age if 'age' in locals() else 99

    return {
        "score": score,
        "wave": label,
        "reasons": reasons[:4],
        "bullish": bullish,
        "rsi": rsi,
        "price": round(current, 6),
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
                "score": analysis["score"],
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