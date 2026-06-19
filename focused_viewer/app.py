#!/usr/bin/env python3
"""
지정종목 엘리어트 분석 뷰어 — 데스크톱 GUI (Flask + pywebview)

기존 엘리어트_지정종목_분석.py 결과를 시각화합니다.
실행: python app.py
EXE: build_exe.bat
"""

from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file
from io import BytesIO

if getattr(sys, "frozen", False):
    APP_DIR = Path(sys._MEIPASS)
else:
    APP_DIR = Path(__file__).resolve().parent

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from analyzer_bridge import (  # noqa: E402
    DEFAULT_TOP_N,
    list_saved_reports,
    load_latest_saved,
    load_report,
    resolve_chart_candles,
    run_analysis,
)
from charts import HAS_MPL, chart_to_base64, generate_chart_bytes  # noqa: E402

app = Flask(
    __name__,
    template_folder=str(APP_DIR / "templates"),
    static_folder=str(APP_DIR / "static"),
)
app.config["JSON_AS_ASCII"] = False

_cache: dict = {"data": None, "scanning": False, "last_error": None}
PORT = int(os.environ.get("PORT", 5789))
IS_PRODUCTION = os.environ.get("RENDER") or os.environ.get("WEB_DEPLOY") or os.environ.get("RAILWAY_ENVIRONMENT")
SCAN_SECRET = os.environ.get("SCAN_SECRET", "")


def _public_result(row: dict) -> dict:
    return {k: v for k, v in row.items() if k not in ("chart_candles", "candles")}


def _serialize_results(data: dict) -> dict:
    if not data:
        return {"generated_at": None, "results": [], "meta": {}}
    results = [_public_result(r) for r in data.get("results", [])]
    bull_summary = sorted(
        [r for r in results if r.get("bull_score", 0) >= 50],
        key=lambda x: x.get("bull_score", 0),
        reverse=True,
    )
    return {
        "generated_at": data.get("generated_at"),
        "interval": data.get("interval", "4h"),
        "top_n": data.get("top_n", DEFAULT_TOP_N),
        "pool": data.get("pool", f"Binance USDT top {data.get('top_n', DEFAULT_TOP_N)} by 24h volume"),
        "source_file": data.get("source_file"),
        "saved_path": data.get("saved_path"),
        "results": results,
        "bull_summary": [
            {"kr": r["kr"], "symbol": r["symbol"], "score": r["bull_score"], "reco": r.get("bull_recommendation", "")}
            for r in bull_summary
        ],
        "coin_count": len(results),
        "has_mpl": HAS_MPL,
    }


@app.route("/")
def index():
    disable_scan = os.environ.get("DISABLE_SCAN", "").lower() in ("1", "true", "yes")
    return render_template(
        "index.html",
        top_n=DEFAULT_TOP_N,
        has_mpl=HAS_MPL,
        allow_scan=not disable_scan,
        is_production=bool(IS_PRODUCTION),
    )


@app.route("/api/status")
def api_status():
    data = _cache.get("data")
    if data is None:
        saved = load_latest_saved()
        if saved:
            _cache["data"] = saved
            data = saved
    return jsonify({
        "scanning": _cache["scanning"],
        "last_error": _cache.get("last_error"),
        "has_data": data is not None,
        "generated_at": data.get("generated_at") if data else None,
    })


@app.route("/api/latest")
def api_latest():
    data = _cache.get("data")
    if data is None:
        data = load_latest_saved()
        if data:
            _cache["data"] = data
    return jsonify(_serialize_results(data or {}))


@app.route("/api/scan", methods=["POST"])
def api_scan():
    if SCAN_SECRET:
        key = request.headers.get("X-Scan-Key") or request.form.get("scan_key", "")
        if key != SCAN_SECRET:
            return jsonify({"success": False, "message": "스캔 권한이 없습니다."}), 403

    if _cache["scanning"]:
        return jsonify({"success": False, "message": "이미 분석 중입니다."}), 409

    interval = request.form.get("interval", "4h")
    lookback = int(request.form.get("lookback", 110))

    def _do_scan():
        _cache["scanning"] = True
        _cache["last_error"] = None
        try:
            if IS_PRODUCTION:
                os.environ["WEB_DEPLOY"] = "1"
            result = run_analysis(interval=interval, lookback=lookback, save=not IS_PRODUCTION)
            _cache["data"] = result
        except Exception as e:
            _cache["last_error"] = str(e)
        finally:
            _cache["scanning"] = False

    threading.Thread(target=_do_scan, daemon=True).start()
    return jsonify({"success": True, "message": "분석을 시작했습니다. 1~2분 후 결과가 표시됩니다."})


@app.route("/api/reports")
def api_reports():
    return jsonify(list_saved_reports())


@app.route("/api/report/<filename>")
def api_report(filename: str):
    data = load_report(filename)
    if not data:
        return jsonify({"error": "파일 없음"}), 404
    _cache["data"] = data
    return jsonify(_serialize_results(data))


@app.route("/api/chart/<symbol>")
def api_chart(symbol: str):
    if not HAS_MPL:
        return "matplotlib 미설치", 400

    data = _cache.get("data") or load_latest_saved()
    if not data:
        return "분석 데이터 없음", 404

    coin = next((r for r in data.get("results", []) if r["symbol"].upper() == symbol.upper()), None)
    if not coin:
        return "종목 없음", 404

    interval = data.get("interval", "4h")
    candles, err = resolve_chart_candles(
        coin, symbol, interval=interval, limit=110, allow_live_fetch=not IS_PRODUCTION
    )
    if err:
        return err, 503 if IS_PRODUCTION else 500
    png = generate_chart_bytes(candles, coin, interval=interval)
    if not png:
        return "차트 생성 실패", 500
    return send_file(BytesIO(png), mimetype="image/png")


@app.route("/api/chart-b64/<symbol>")
def api_chart_b64(symbol: str):
    if not HAS_MPL:
        return jsonify({"error": "matplotlib 미설치"}), 400

    data = _cache.get("data") or load_latest_saved()
    if not data:
        return jsonify({"error": "데이터 없음"}), 404

    coin = next((r for r in data.get("results", []) if r["symbol"].upper() == symbol.upper()), None)
    if not coin:
        return jsonify({"error": "종목 없음"}), 404

    interval = data.get("interval", "4h")
    candles, err = resolve_chart_candles(
        coin, symbol, interval=interval, limit=110, allow_live_fetch=not IS_PRODUCTION
    )
    if err:
        return jsonify({"error": err}), 503 if IS_PRODUCTION else 500
    png = generate_chart_bytes(candles, coin, interval=interval)
    b64 = chart_to_base64(png)
    if not b64:
        return jsonify({"error": "차트 생성 실패 (matplotlib)"}), 500
    return jsonify({"image": b64, "symbol": symbol})


def _wait_for_server(timeout: float = 8.0) -> bool:
    import urllib.request
    url = f"http://127.0.0.1:{PORT}/api/status"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.2)
    return False


def start_flask():
    host = "0.0.0.0" if IS_PRODUCTION else "127.0.0.1"
    app.run(host=host, port=PORT, debug=False, use_reloader=False, threaded=True)


def main(use_webview: bool = True):
    saved = load_latest_saved()
    if saved:
        _cache["data"] = saved
        print(f"[로드] 최근 저장 결과: {saved.get('source_file', 'unknown')}")

    server_thread = threading.Thread(target=start_flask, daemon=True)
    server_thread.start()

    if not _wait_for_server():
        print("[오류] 서버 시작 실패")
        sys.exit(1)

    url = f"http://127.0.0.1:{PORT}"

    if use_webview:
        try:
            import webview
            webview.create_window(
                "지정종목 엘리어트 분석 뷰어",
                url,
                width=1280,
                height=860,
                min_size=(900, 600),
            )
            webview.start()
            return
        except ImportError:
            print("[안내] pywebview 미설치 → 브라우저로 열기")

    webbrowser.open(url)
    print(f"[실행] {url}")
    print("종료하려면 Ctrl+C")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    if IS_PRODUCTION or "--server" in sys.argv:
        saved = load_latest_saved()
        if saved:
            _cache["data"] = saved
        start_flask()
    else:
        no_webview = "--browser" in sys.argv
        main(use_webview=not no_webview)