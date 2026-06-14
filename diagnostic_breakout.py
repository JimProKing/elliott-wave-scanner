from backtest_elliott_accuracy import fetch_long_history, _analyze_elliott_structure

for sym in ["BTCUSDT", "SOLUSDT", "XRPUSDT"]:
    hist = fetch_long_history(sym, "4h", 300)
    lookback = 85
    breakout_count = 0
    strong_count = 0
    for i in range(lookback + 10, len(hist) - 5):
        an = _analyze_elliott_structure(hist[i-lookback:i])
        if an.get("bullish"):
            reasons = " ".join(an.get("reasons", []))
            if "이전 고점 돌파" in reasons:
                breakout_count += 1
            if an["score"] >= 68:
                strong_count += 1
    total_windows = len(hist) - lookback
    print(f"{sym}: '조정 후 이전 고점 돌파' triggered in {breakout_count}/{total_windows} windows ({breakout_count/total_windows*100:.1f}%) | strong signals (>=68): {strong_count}")
print("Done.")