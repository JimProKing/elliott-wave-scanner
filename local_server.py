#!/usr/bin/env python3
"""
Local web server for Elliott Wave Scanner results.
Run this on your machine while it's on.
Others can access via ngrok (or similar tunnel) while your PC is running.

Usage:
  pip install flask
  python local_server.py
  # In another terminal:
  ngrok http 5000   # share the https URL
"""

from flask import Flask, jsonify, request, send_file
import subprocess
import threading
import time
import json
from pathlib import Path
from datetime import datetime

app = Flask(__name__, static_folder="web", static_url_path="/static")

RESULTS_DIR = Path("results")
SCAN_LOCK = threading.Lock()
SCANNING = False

# 종목 리스트 폴더 (바이낸스/종목/)
# 종목 리스트 폴더 - 여러 위치 시도 (실행 위치에 따라 유연하게)
_possible_stock_dirs = [
    Path(__file__).parent.parent / "바이낸스" / "종목",
    Path(__file__).parent / "바이낸스" / "종목",  # 만약 하위에 복사된 경우
    Path("C:/Users/a/Documents/Trading/바이낸스/종목"),  # 절대 경로 fallback
]
STOCK_LIST_DIR = None
for d in _possible_stock_dirs:
    if d.exists():
        STOCK_LIST_DIR = d
        break
if STOCK_LIST_DIR is None:
    STOCK_LIST_DIR = _possible_stock_dirs[0]  # fallback (리스트 함수에서 처리)

def run_scan():
    """Run the scanner in background."""
    global SCANNING
    with SCAN_LOCK:
        if SCANNING:
            return False
        SCANNING = True

    try:
        # 스캐너 실행 (같은 폴더에 있어야 함)
        result = subprocess.run(
            ["python", "elliott_wave_scanner.py", "--json", "--output-dir", "results"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent,
            timeout=300  # 최대 5분
        )
        print("스캔 출력:", result.stdout)
        if result.stderr:
            print("스캔 에러:", result.stderr)
        return True
    except Exception as e:
        print("스캔 실패:", e)
        return False
    finally:
        SCANNING = False

def get_latest_data():
    """Load the latest scan results."""
    latest = RESULTS_DIR / "latest.json"
    if not latest.exists():
        return {
            "generated_at": None,
            "candidates": [],
            "meta": {"note": "No scan results yet. Click Run Scan."}
        }
    with open(latest, "r", encoding="utf-8") as f:
        return json.load(f)

def list_stock_lists():
    """종목리스트_생성.py 결과 파일 목록 (최신순)"""
    if not STOCK_LIST_DIR.exists():
        return []
    files = []
    for f in STOCK_LIST_DIR.glob("*_종목들.txt"):
        try:
            # 파일명에서 타임스탬프 추출
            ts_str = f.stem.split("_")[0] + "_" + f.stem.split("_")[1]
            dt = datetime.strptime(ts_str, "%Y%m%d_%H%M")
            files.append({
                "filename": f.name,
                "path": str(f),
                "generated_at": dt.isoformat(),
                "size": f.stat().st_size
            })
        except Exception:
            files.append({
                "filename": f.name,
                "path": str(f),
                "generated_at": None,
                "size": f.stat().st_size
            })
    files.sort(key=lambda x: x["generated_at"] or "", reverse=True)
    return files

def get_stock_list_content(filename: str):
    """파일 내용 반환"""
    filepath = STOCK_LIST_DIR / filename
    if not filepath.exists() or not filename.endswith("_종목들.txt"):
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()

def run_stock_list_generator():
    """종목리스트_생성.py 실행"""
    script_path = STOCK_LIST_DIR / "종목리스트_생성.py"
    if not script_path.exists():
        return {"success": False, "error": "종목리스트_생성.py not found"}
    try:
        result = subprocess.run(
            ["python", str(script_path)],
            capture_output=True,
            text=True,
            cwd=STOCK_LIST_DIR,
            timeout=120
        )
        # 새 파일 찾기 (가장 최근)
        new_files = list_stock_lists()
        new_file = new_files[0]["filename"] if new_files else None
        return {
            "success": True,
            "output": result.stdout,
            "new_file": new_file
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

# 간단하고 예쁜 UI (Tailwind CDN, 로컬용으로 한국어화)
HTML = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>엘리어트 웨이브 스캐너 • 로컬</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
        body { font-family: system-ui, -apple-system, sans-serif; }
        .score-high { color: #22c55e; font-weight: 700; }
        @media (max-width: 640px) {
            .mobile-compact th, .mobile-compact td { padding-left: 0.5rem; padding-right: 0.5rem; padding-top: 0.375rem; padding-bottom: 0.375rem; font-size: 0.75rem; }
            .mobile-compact table { font-size: 0.75rem; }
        }
    </style>
</head>
<body class="bg-slate-950 text-slate-200">
    <div class="max-w-6xl mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-6 gap-4">
            <div>
                <h1 class="text-2xl sm:text-3xl font-bold flex items-center gap-3">
                    <i class="fa-solid fa-chart-line text-emerald-400"></i>
                    엘리어트 웨이브 스캐너 (로컬)
                </h1>
                <p class="text-slate-400 mt-1 text-sm sm:text-base">상위 100개 USDT 페어 • 4h • 내 컴퓨터에서 실행</p>
            </div>
            <div class="w-full sm:w-auto">
                <button onclick="runScan()"
                        class="w-full sm:w-auto px-5 py-3 sm:px-6 sm:py-2.5 bg-emerald-600 hover:bg-emerald-500 active:bg-emerald-700 rounded-2xl font-semibold flex items-center justify-center gap-2 text-base">
                    <i class="fa-solid fa-play"></i>
                    <span id="run-btn-text">지금 스캔 실행</span>
                </button>
                <div id="scan-status" class="text-xs text-emerald-400 mt-1 text-right"></div>
            </div>
        </div>

        <div class="bg-slate-900 border border-slate-800 rounded-2xl p-3 sm:p-4 mb-6">
            <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                <div>
                    <div class="text-xs sm:text-sm text-slate-400">마지막 스캔</div>
                    <div id="last-updated" class="font-medium text-sm sm:text-base">불러오는 중...</div>
                </div>
                <div class="text-[10px] sm:text-xs px-2 py-1 sm:px-3 sm:py-1 bg-slate-800 rounded-full self-start sm:self-auto">
                    PC가 켜져 있고 터널이 실행 중일 때만 공개됩니다
                </div>
            </div>
        </div>

        <div class="bg-slate-900 border border-slate-800 rounded-3xl overflow-hidden">
            <div class="px-3 sm:px-6 py-3 sm:py-4 border-b border-slate-800 flex items-center justify-between">
                <div class="font-semibold text-base sm:text-lg">최신 후보 종목</div>
                <div id="candidate-count" class="text-xs sm:text-sm text-slate-400"></div>
            </div>

            <div class="overflow-x-auto">
                <table class="w-full text-xs sm:text-sm mobile-compact">
                    <thead>
                        <tr class="text-left border-b border-slate-800">
                            <th class="px-2 sm:px-6 py-2 sm:py-3">#</th>
                            <th class="px-2 sm:px-4 py-2 sm:py-3">심볼</th>
                            <th class="px-2 sm:px-4 py-2 sm:py-3">점수</th>
                            <th class="px-2 sm:px-4 py-2 sm:py-3">가격</th>
                            <th class="px-2 sm:px-4 py-2 sm:py-3">거래량 (24h)</th>
                            <th class="px-2 sm:px-4 py-2 sm:py-3">RSI</th>
                            <th class="px-2 sm:px-4 py-2 sm:py-3">평가</th>
                            <th class="px-2 sm:px-4 py-2 sm:py-3">이유</th>
                            <th class="px-2 sm:px-4 py-2 sm:py-3">매매 레벨</th>
                        </tr>
                    </thead>
                    <tbody id="results-body" class="divide-y divide-slate-800"></tbody>
                </table>
            </div>
        </div>

        <div class="mt-6 text-[10px] sm:text-xs text-slate-500">
            <p>• 이 페이지는 <strong>내 로컬 컴퓨터</strong>에서 ngrok 같은 터널을 통해 제공됩니다.</p>
            <p>• "지금 스캔 실행" 버튼을 누르면 PC에서 새로운 스캔이 시작되고 결과가 자동으로 업데이트됩니다.</p>
            <p>• 서버와 터널을 계속 켜두면 다른 사람들이 최신 데이터를 볼 수 있습니다.</p>
        </div>

        <!-- 종목 리스트 섹션 (종목리스트_생성.py 결과) -->
        <div class="mt-8 bg-slate-900 border border-slate-800 rounded-2xl p-4 sm:p-6">
            <div class="flex flex-col sm:flex-row sm:items-center justify-between mb-4 gap-3">
                <div>
                    <h2 class="text-lg sm:text-xl font-semibold flex items-center gap-2">
                        <i class="fa-solid fa-list"></i>
                        종목 리스트 (종목리스트_생성.py 결과)
                    </h2>
                    <p class="text-xs text-slate-400">바이낸스/종목/ 폴더의 상위 거래량 종목 목록</p>
                </div>
                <button onclick="generateStockList()"
                        class="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded-xl text-sm font-medium flex items-center gap-2 self-start sm:self-auto">
                    <i class="fa-solid fa-sync"></i>
                    <span>새 목록 생성</span>
                </button>
            </div>

            <div id="stock-lists-list" class="mb-4 text-sm">
                <!-- JS로 최근 파일 목록 채움 -->
                <div class="text-slate-400 text-xs">불러오는 중...</div>
            </div>

            <div id="stock-list-content" class="hidden bg-black/50 rounded-xl p-4 text-xs font-mono whitespace-pre-wrap max-h-[400px] overflow-auto border border-slate-700">
                <!-- 선택한 파일 내용 표시 -->
            </div>
        </div>
    </div>

    <script>
        let isScanning = false;

        async function loadResults() {
            try {
                const res = await fetch('/api/latest?t=' + Date.now());
                if (!res.ok) throw new Error('데이터 없음');
                const data = await res.json();

                const updatedEl = document.getElementById('last-updated');
                if (data.generated_at) {
                    updatedEl.textContent = new Date(data.generated_at).toLocaleString();
                } else {
                    updatedEl.textContent = '아직 스캔 결과가 없습니다';
                }

                const tbody = document.getElementById('results-body');
                tbody.innerHTML = '';
                const countEl = document.getElementById('candidate-count');

                if (!data.candidates || data.candidates.length === 0) {
                    countEl.textContent = '0개 후보';
                    tbody.innerHTML = `<tr><td colspan="9" class="px-3 sm:px-6 py-6 sm:py-8 text-center text-slate-400">후보가 없습니다. '지금 스캔 실행'을 눌러주세요.</td></tr>`;
                    return;
                }

                countEl.textContent = `${data.candidates.length}개 후보`;

                data.candidates.forEach((c, i) => {
                    const volM = c.volume_24h ? (c.volume_24h / 1000000).toFixed(1) + 'M' : 'N/A';
                    const leg = c.meta && c.meta.leg_pct ? `+${c.meta.leg_pct}%` : '';
                    const age = c.meta && c.meta.breakout_age_bars != null ? `${c.meta.breakout_age_bars} bars` : '';

                    const row = document.createElement('tr');
                    row.className = 'hover:bg-slate-800/50';
                        const displayScore = c.raw_score ? `${c.score} (raw ${c.raw_score})` : c.score;
                    row.innerHTML = `
                        <td class="px-2 sm:px-6 py-2 sm:py-3 font-mono text-slate-400">${i+1}</td>
                        <td class="px-2 sm:px-4 py-2 sm:py-3 font-semibold text-white">${c.symbol}</td>
                        <td class="px-2 sm:px-4 py-2 sm:py-3"><span class="score-high">${displayScore}</span></td>
                        <td class="px-2 sm:px-4 py-2 sm:py-3 font-mono">${c.price}</td>
                        <td class="px-2 sm:px-4 py-2 sm:py-3">${volM}</td>
                        <td class="px-2 sm:px-4 py-2 sm:py-3">${c.rsi ? c.rsi.toFixed(1) : '-'}</td>
                        <td class="px-2 sm:px-4 py-2 sm:py-3 text-emerald-400 text-xs">${c.wave}</td>
                        <td class="px-2 sm:px-4 py-2 sm:py-3 text-xs text-slate-400">${c.reasons ? c.reasons.join(' • ') : ''}</td>
                        <td class="px-2 sm:px-4 py-2 sm:py-3 text-xs">
                            <div>진입가: <span class="font-mono">${c.entry}</span></div>
                            <div class="text-emerald-400">익절가: ${c.tp}</div>
                            <div class="text-red-400">손절가: ${c.sl}</div>
                            <div class="text-[10px] text-slate-500 mt-0.5">${leg} ${age}</div>
                        </td>
                    `;
                    tbody.appendChild(row);
                });
            } catch (e) {
                console.error(e);
                document.getElementById('results-body').innerHTML = 
                    `<tr><td colspan="9" class="px-3 sm:px-6 py-6 sm:py-8 text-center text-red-400">결과를 불러오지 못했습니다. 서버가 실행 중인지 확인하세요.</td></tr>`;
            }
        }

        async function runScan() {
            if (isScanning) return;
            isScanning = true;
            const btn = document.getElementById('run-btn-text');
            const status = document.getElementById('scan-status');
            btn.textContent = '스캔 중...';
            status.textContent = '컴퓨터에서 스캔을 시작했습니다...';

            try {
                const res = await fetch('/api/run', { method: 'POST' });
                const data = await res.json();
                status.textContent = data.message || '스캔 완료. 새로고침 중...';
                
                // 스캔이 끝날 시간을 주고 데이터 새로고침
                setTimeout(() => {
                    loadResults();
                    status.textContent = '';
                    btn.textContent = '지금 스캔 실행';
                    isScanning = false;
                }, 8000);
            } catch (e) {
                console.error(e);
                status.textContent = '스캔 시작에 실패했습니다.';
                btn.textContent = '지금 스캔 실행';
                isScanning = false;
            }
        }

        // 초기 로드
        loadResults();
        loadStockLists();
        // 60초마다 자동 새로고침
        setInterval(loadResults, 60000);
        setInterval(loadStockLists, 120000);  // 종목 리스트는 덜 자주

        async function loadStockLists() {
            try {
                const res = await fetch('/api/stock-lists?t=' + Date.now());
                const lists = await res.json();
                const container = document.getElementById('stock-lists-list');
                container.innerHTML = '';

                if (!lists || lists.length === 0) {
                    container.innerHTML = '<div class="text-slate-400 text-xs">생성된 종목 리스트가 없습니다. "새 목록 생성" 버튼을 눌러보세요.</div>';
                    return;
                }

                const ul = document.createElement('div');
                ul.className = 'grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm';

                lists.slice(0, 6).forEach(item => {  // 최근 6개만
                    const div = document.createElement('div');
                    const date = item.generated_at ? new Date(item.generated_at).toLocaleString('ko-KR', {month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit'}) : 'unknown';
                    div.className = 'bg-slate-800 hover:bg-slate-700 px-3 py-2 rounded-lg cursor-pointer flex justify-between items-center text-xs sm:text-sm';
                    div.innerHTML = `
                        <span class="font-mono">${item.filename}</span>
                        <span class="text-[10px] text-slate-400">${date}</span>
                    `;
                    div.onclick = () => loadStockListContent(item.filename, div);
                    ul.appendChild(div);
                });

                container.appendChild(ul);
            } catch (e) {
                document.getElementById('stock-lists-list').innerHTML = '<div class="text-red-400 text-xs">종목 리스트 로드 실패</div>';
            }
        }

        async function loadStockListContent(filename, clickedEl) {
            const contentDiv = document.getElementById('stock-list-content');
            contentDiv.classList.remove('hidden');
            contentDiv.innerHTML = `<div class="text-slate-400">불러오는 중: ${filename} ...</div>`;

            try {
                const res = await fetch(`/api/stock-list/${encodeURIComponent(filename)}`);
                const data = await res.json();
                if (data.error) throw new Error(data.error);

                // 상위 100개 부분을 강조해서 보여주기
                let html = `<div class="font-bold mb-2">📄 ${filename}</div>`;
                html += `<div class="text-[10px] text-slate-400 mb-2">(전체 내용은 아래. 상위 100개는 상단 섹션 참고)</div>`;
                html += `<pre class="text-[11px] leading-tight whitespace-pre-wrap">${data.content.substring(0, 8000)}${data.content.length > 8000 ? '\n... (생략됨)' : ''}</pre>`;
                contentDiv.innerHTML = html;

                // 이전 선택 표시 제거
                document.querySelectorAll('#stock-lists-list > div > div').forEach(el => el.classList.remove('ring-2', 'ring-blue-500'));
                if (clickedEl) clickedEl.classList.add('ring-2', 'ring-blue-500');
            } catch (e) {
                contentDiv.innerHTML = `<div class="text-red-400">로드 실패: ${e.message}</div>`;
            }
        }

        async function generateStockList() {
            const btns = document.querySelectorAll('#stock-lists-list button, .bg-blue-600');
            const status = document.getElementById('stock-lists-list');
            status.innerHTML = '<div class="text-blue-400 text-xs">종목 리스트 생성 중... (1~2분 소요될 수 있음)</div>';

            try {
                const res = await fetch('/api/generate-stock-list', { method: 'POST' });
                const data = await res.json();
                if (!data.success) throw new Error(data.error || '생성 실패');

                status.innerHTML = `<div class="text-green-400 text-xs">✅ 새 목록 생성됨: ${data.new_file || ''}</div>`;
                await loadStockLists();

                // 새로 생성된 파일 자동 로드
                if (data.new_file) {
                    setTimeout(() => {
                        const container = document.getElementById('stock-lists-list');
                        // 첫 번째 항목 클릭 시뮬레이션
                        const first = container.querySelector('div[onclick]');
                        if (first) first.click();
                    }, 500);
                }
            } catch (e) {
                status.innerHTML = `<div class="text-red-400 text-xs">생성 실패: ${e.message}</div>`;
                setTimeout(loadStockLists, 2000);
            }
        }
    </script>
</body>
</html>
"""

@app.route("/")
def index():
    return HTML

@app.route("/api/latest")
def api_latest():
    data = get_latest_data()
    return jsonify(data)

@app.route("/api/run", methods=["POST"])
def api_run():
    global SCANNING
    if SCANNING:
        return jsonify({"status": "busy", "message": "이미 스캔이 진행 중입니다."}), 409

    # 요청을 바로 반환하고 백그라운드에서 실행
    threading.Thread(target=run_scan, daemon=True).start()
    return jsonify({
        "status": "started",
        "message": "백그라운드에서 스캔을 시작했습니다. 30~90초 후 결과가 업데이트됩니다."
    })

@app.route("/api/stock-lists")
def api_stock_lists():
    return jsonify(list_stock_lists())

@app.route("/api/stock-list/<filename>")
def api_stock_list(filename):
    content = get_stock_list_content(filename)
    if content is None:
        return jsonify({"error": "File not found"}), 404
    return jsonify({"filename": filename, "content": content})

@app.route("/api/generate-stock-list", methods=["POST"])
def api_generate_stock_list():
    result = run_stock_list_generator()
    return jsonify(result)

if __name__ == "__main__":
    RESULTS_DIR.mkdir(exist_ok=True)
    print("=" * 50)
    print("  엘리어트 웨이브 스캐너 - 로컬 웹서버 시작")
    print("=" * 50)
    print("")
    print(" [로컬 접속] http://127.0.0.1:5000")
    print(" [모바일 친화적] 반응형 레이아웃 적용 (표 가로스크롤 + 모바일 최적화)")
    print("")
    print(" [추가 기능] 종목 리스트 보기 + 생성 지원 (바이낸스/종목/ 결과)")
    print("")
    print(" [외부 공개 방법]")
    print("   1. 새 터미널에서 다음 명령어 실행:")
    print("      ngrok http 5000")
    print("   2. ngrok이 주는 https://... 주소 복사")
    print("   3. 그 주소를 다른 사람에게 공유 (모바일에서도 잘 보임)")
    print("")
    print(" [중요]")
    print("   - PC가 켜져 있고 이 서버 + ngrok이 실행 중일 때만 공개됩니다.")
    print("   - '지금 스캔 실행' 버튼을 누르면 이 컴퓨터에서 실제 스캔이 시작됩니다.")
    print("")
    print(" ngrok이 없으면 https://ngrok.com/download 에서 다운로드하세요.")
    print("=" * 50)
    print("")
    app.run(host="0.0.0.0", port=5000, debug=False)