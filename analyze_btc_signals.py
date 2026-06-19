from backtest_elliott_accuracy import fetch_long_history, _analyze_elliott_structure

for sym in ["BTCUSDT", "SOLUSDT", "XRPUSDT"]:
    hist = fetch_long_history(sym, "4h", 420)
    print(f"\n{sym}: {len(hist)} bars (~{len(hist)*4/24:.1f}d)")

    lookback = 85
    signals = []
    for i in range(lookback + 15, len(hist) - 25):
        slc = hist[i-lookback:i]
        an = _analyze_elliott_structure(slc)
        if an.get("bullish") and an["score"] >= 62:  # 개선된 로직 기준 (70+ 는 매우 엄격, 62+ 로 실용적 고품질 후보 측정)
            entry = an["current_price"]
            struct_low = min(c["low"] for c in slc[-25:])
            sl = round(struct_low * 0.985, 8)
            if entry <= sl:
                sl = round(entry * 0.95, 8)
            risk = entry - sl
            tp = round(entry + risk * 1.272, 8)  # 개선 버전과 일치 (현실적 1차 타겟)

            max_fwd = 48
            jmax = min(i + max_fwd, len(hist))
            fwd_highs = [hist[j]["high"] for j in range(i, jmax)]
            fwd_lows = [hist[j]["low"] for j in range(i, jmax)]
            fwd_cls = [hist[j]["close"] for j in range(i, jmax)]

            reached_tp = any(h >= tp for h in fwd_highs)
            hit_sl = any(l <= sl for h in fwd_lows)
            max_up = (max(fwd_highs) - entry) / entry * 100.0
            min_low = (min(fwd_lows) - entry) / entry * 100.0
            end_move = (fwd_cls[-1] - entry) / entry * 100.0 if fwd_cls else 0

            # Practical 1R (risk 1배) 달성 — scanner TP(1.272)보다 현실적 최소 승률 지표
            one_r = entry + (entry - sl) * 1.0
            reached_1r = any(h >= one_r for h in fwd_highs)

            signals.append({
                "score": an["score"],
                "entry": entry,
                "tp": tp,
                "sl": sl,
                "reached_tp": reached_tp,
                "reached_1r": reached_1r,
                "hit_sl_first": hit_sl and not reached_tp,
                "max_up_pct": round(max_up, 1),
                "min_dd_pct": round(min_low, 1),
                "end_8d_pct": round(end_move, 1),
            })

    print(f"  High-quality bullish signals (score>=62, improved logic): {len(signals)}")
    if signals:
        tp_hits = sum(1 for s in signals if s["reached_tp"])
        one_r_hits = sum(1 for s in signals if s.get("reached_1r"))
        sl_hits = sum(1 for s in signals if s["hit_sl_first"])
        avg_best = sum(s["max_up_pct"] for s in signals) / len(signals)
        avg_end = sum(s["end_8d_pct"] for s in signals) / len(signals)
        print(f"  TP (1.272x) reached (~8d): {tp_hits} / {len(signals)} = {tp_hits/len(signals)*100:.1f}%")
        print(f"  At least 1R (risk x1.0) reached: {one_r_hits} / {len(signals)} = {one_r_hits/len(signals)*100:.1f}%  <--- practical win metric")
        print(f"  SL hit first (no TP): {sl_hits} / {len(signals)} = {sl_hits/len(signals)*100:.1f}%")
        print(f"  Avg best favorable move: +{avg_best:.1f}%")
        print(f"  Avg +8d outcome: {avg_end:+.1f}%")
print("\nDone.")