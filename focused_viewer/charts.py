"""지정종목 엘리어트 분석 차트 생성 (최근 3일 · 가독성 우선)."""

from __future__ import annotations

import base64
from datetime import datetime
from io import BytesIO
from typing import Dict, List, Optional

CHART_DISPLAY_DAYS = 3
CHART_MIN_CANDLES = 8

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    HAS_MPL = True
except ImportError:
    HAS_MPL = False


def _bias_label_en(bias: str) -> str:
    if "강력 롱" in bias:
        return "Strong LONG"
    if "강한 롱" in bias:
        return "LONG bias"
    if "강력 숏" in bias:
        return "Strong SHORT"
    if "강한 숏" in bias:
        return "SHORT bias"
    if "상승 Setup" in bias:
        return "Bull setup"
    if "하락 Setup" in bias:
        return "Bear setup"
    return "Neutral"


def _trim_candles(candles: List[Dict], days: int = CHART_DISPLAY_DAYS, interval: str = "1h") -> List[Dict]:
    if not candles:
        return []
    hours_per_bar = 1 if interval == "1h" else 4 if interval == "4h" else 1
    max_bars = max(CHART_MIN_CANDLES, int(days * 24 / hours_per_bar))
    return candles[-max_bars:]


def generate_chart_bytes(
    candles: List[Dict],
    coin_info: Dict,
    interval: str = "1h",
    *,
    display_days: int = CHART_DISPLAY_DAYS,
) -> Optional[bytes]:
    if not HAS_MPL:
        return None

    candles = _trim_candles(candles, days=display_days, interval=interval)
    if len(candles) < CHART_MIN_CANDLES:
        return None

    sym = coin_info.get("symbol", "")
    bull_s = coin_info.get("bull_score", 0)
    bear_s = coin_info.get("bear_score", 0)
    bias_en = _bias_label_en(coin_info.get("overall_bias", ""))

    times = [datetime.fromtimestamp(c["open_time"] / 1000) for c in candles]
    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]

    fig, ax = plt.subplots(figsize=(12, 5), facecolor="#0f172a")
    ax.set_facecolor("#1e293b")
    for spine in ax.spines.values():
        spine.set_color("#334155")
    ax.tick_params(colors="#cbd5e1", labelsize=10)
    ax.grid(True, alpha=0.2, color="#475569", linestyle="-", linewidth=0.6)

    ax.fill_between(times, lows, highs, color="#334155", alpha=0.35, linewidth=0)
    ax.plot(times, closes, color="#38bdf8", linewidth=2.2, label="Close", zorder=3)

    long_lv = coin_info.get("long_levels", {})
    short_lv = coin_info.get("short_levels", {})
    price_min, price_max = min(lows), max(highs)
    margin = (price_max - price_min) * 0.08 or price_max * 0.01

    for price, color, label in (
        (long_lv.get("entry"), "#22c55e", "Long entry"),
        (long_lv.get("sl"), "#ef4444", "Long SL"),
        (short_lv.get("entry"), "#f97316", "Short entry"),
        (short_lv.get("sl"), "#fb7185", "Short SL"),
    ):
        if price and price > 0 and price_min - margin <= price <= price_max + margin:
            ax.axhline(price, color=color, linestyle="--", linewidth=1.4, alpha=0.9, label=label)

    title = f"{sym}  |  Bull {bull_s}  /  Bear {bear_s}  |  {bias_en}"
    ax.set_title(title, fontsize=13, color="#f8fafc", pad=12, fontweight="bold")
    ax.set_ylabel("Price (USDT)", color="#94a3b8", fontsize=11)

    if interval == "1h":
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d %H:%M"))
    else:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=0, ha="center", color="#cbd5e1")

    ax.legend(loc="upper left", fontsize=9, framealpha=0.35, facecolor="#0f172a", labelcolor="#e2e8f0")
    fig.text(
        0.99, 0.02,
        f"Last {display_days} days · {interval}",
        ha="right", va="bottom", fontsize=9, color="#64748b",
    )
    plt.tight_layout()

    buf = BytesIO()
    plt.savefig(buf, format="png", dpi=120, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def chart_to_base64(png_bytes: Optional[bytes]) -> Optional[str]:
    if not png_bytes:
        return None
    return base64.b64encode(png_bytes).decode("ascii")