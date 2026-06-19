"""지정종목 엘리어트 분석 차트 생성."""

from __future__ import annotations

import base64
from datetime import datetime
from io import BytesIO
from typing import Dict, List, Optional

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.patches import Rectangle
    HAS_MPL = True
except ImportError:
    HAS_MPL = False


def _setup_korean_font():
    if not HAS_MPL:
        return
    import matplotlib.font_manager as fm
    candidates = ["Malgun Gothic", "NanumGothic", "AppleGothic", "DejaVu Sans"]
    available = {f.name for f in fm.fontManager.ttflist}
    for name in candidates:
        if name in available:
            plt.rcParams["font.family"] = name
            plt.rcParams["axes.unicode_minus"] = False
            return
    plt.rcParams["axes.unicode_minus"] = False


def _find_swings(closes: List[float], window: int = 3, min_move_pct: float = 0.012) -> List[Dict]:
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
    if not raw:
        return []
    filtered = [raw[0]]
    for s in raw[1:]:
        prev = filtered[-1]["price"]
        if prev > 0 and abs(s["price"] - prev) / prev >= min_move_pct:
            filtered.append(s)
    return filtered


def _calc_rsi(closes: List[float], period: int = 14) -> List[Optional[float]]:
    if len(closes) < period + 1:
        return [None] * len(closes)
    rsi_vals: List[Optional[float]] = [None] * period
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    for i in range(period, len(closes)):
        ag = sum(gains[i - period:i]) / period
        al = sum(losses[i - period:i]) / period
        if al == 0:
            rsi_vals.append(100.0)
        else:
            rsi_vals.append(100 - (100 / (1 + ag / al)))
    return rsi_vals


def generate_chart_bytes(
    candles: List[Dict],
    coin_info: Dict,
    interval: str = "4h",
) -> Optional[bytes]:
    if not HAS_MPL or len(candles) < 20:
        return None

    _setup_korean_font()

    times = [datetime.fromtimestamp(c["open_time"] / 1000) for c in candles]
    opens = [c["open"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    closes = [c["close"] for c in candles]
    swings = _find_swings(closes)
    rsi = _calc_rsi(closes)

    kr = coin_info.get("kr", "")
    sym = coin_info.get("symbol", "")
    bull_s = coin_info.get("bull_score", 0)
    bear_s = coin_info.get("bear_score", 0)
    bias = coin_info.get("overall_bias", "")
    long_lv = coin_info.get("long_levels", {})
    short_lv = coin_info.get("short_levels", {})

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(11, 7),
        gridspec_kw={"height_ratios": [3, 1]},
        sharex=True,
        facecolor="#0f172a",
    )

    for ax in (ax1, ax2):
        ax.set_facecolor("#1e293b")
        ax.tick_params(colors="#94a3b8")
        for spine in ax.spines.values():
            spine.set_color("#334155")

    width = 0.6
    for i, t in enumerate(times):
        o, h, l, c = opens[i], highs[i], lows[i], closes[i]
        color = "#22c55e" if c >= o else "#ef4444"
        ax1.plot([t, t], [l, h], color=color, linewidth=0.8, alpha=0.9)
        body_bottom = min(o, c)
        body_h = max(abs(c - o), (h - l) * 0.02)
        rect = Rectangle(
            (mdates.date2num(t) - width / 2, body_bottom),
            width, body_h,
            facecolor=color, edgecolor=color, alpha=0.85,
        )
        ax1.add_patch(rect)

    for s in swings[-10:]:
        idx = s["idx"]
        if idx >= len(times):
            continue
        t = times[idx]
        if s["type"] == "high":
            ax1.scatter(t, s["price"], marker="v", s=70, color="#fbbf24", zorder=5, edgecolors="#0f172a")
        else:
            ax1.scatter(t, s["price"], marker="^", s=70, color="#38bdf8", zorder=5, edgecolors="#0f172a")

    level_styles = [
        (long_lv.get("entry"), "#22c55e", "Long Entry", "-"),
        (long_lv.get("sl"), "#ef4444", "Long SL", "--"),
        (long_lv.get("tp1"), "#4ade80", "Long TP1", ":"),
        (short_lv.get("sl"), "#f87171", "Short SL", "--"),
        (short_lv.get("tp1"), "#fb923c", "Short TP1", ":"),
    ]
    for price, color, label, ls in level_styles:
        if price and price > 0:
            ax1.axhline(price, color=color, linestyle=ls, linewidth=1.0, alpha=0.75, label=label)

    title = f"{kr} ({sym})  |  상승 {bull_s}점 / 하락 {bear_s}점  |  {bias}"
    ax1.set_title(title, fontsize=12, color="#f1f5f9", pad=10)
    ax1.set_ylabel("Price", color="#94a3b8")
    ax1.legend(loc="upper left", fontsize=7, framealpha=0.3, facecolor="#1e293b", labelcolor="#e2e8f0")
    ax1.grid(True, alpha=0.15, color="#475569")

    rsi_x = [t for t, v in zip(times, rsi) if v is not None]
    rsi_y = [v for v in rsi if v is not None]
    if rsi_x:
        ax2.plot(rsi_x, rsi_y, color="#a78bfa", linewidth=1.2)
        ax2.axhline(70, color="#ef4444", linestyle="--", linewidth=0.8, alpha=0.6)
        ax2.axhline(30, color="#22c55e", linestyle="--", linewidth=0.8, alpha=0.6)
        ax2.fill_between(rsi_x, 30, 70, alpha=0.08, color="#a78bfa")
    ax2.set_ylim(0, 100)
    ax2.set_ylabel("RSI", color="#94a3b8")
    ax2.grid(True, alpha=0.15, color="#475569")
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d %H:%M"))
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=30, ha="right", color="#94a3b8")

    fig.text(0.99, 0.01, f"TF: {interval}", ha="right", va="bottom", fontsize=8, color="#64748b")
    plt.tight_layout()

    buf = BytesIO()
    plt.savefig(buf, format="png", dpi=130, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def chart_to_base64(png_bytes: Optional[bytes]) -> Optional[str]:
    if not png_bytes:
        return None
    return base64.b64encode(png_bytes).decode("ascii")