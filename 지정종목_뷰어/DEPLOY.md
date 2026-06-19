# 지정종목 엘리어트 뷰어 — 웹 배포 가이드

로컬 `http://127.0.0.1:5789` 와 동일한 UI를 인터넷에 공개하는 방법입니다.

## 추천 구성 (무료)

| 역할 | 서비스 | 설명 |
|------|--------|------|
| 웹 서버 | **Render.com** (무료) | Flask 앱 호스팅, 차트 생성 |
| 자동 분석 | **GitHub Actions** | 4시간마다 분석 → `data/latest.json` 갱신 |

이렇게 하면 PC를 켜두지 않아도 누구나 URL로 접속해 최신 결과를 볼 수 있습니다.

---

## 1단계: GitHub에 올리기

```bash
cd C:\Users\a\Documents\Trading\elliott-wave-scanner
git init
git add .
git commit -m "Add focused coin viewer for web deploy"
```

GitHub에서 새 **Public** 저장소를 만든 뒤:

```bash
git remote add origin https://github.com/YOUR_USERNAME/elliott-wave-scanner.git
git branch -M main
git push -u origin main
```

### GitHub Actions 권한 (필수)

저장소 → **Settings** → **Actions** → **General**

- Workflow permissions → **Read and write permissions** 선택

### 첫 분석 실행

**Actions** 탭 → **Focused Coin Scan (지정종목)** → **Run workflow**

성공하면 `지정종목_뷰어/data/latest.json` 이 자동 커밋됩니다.

---

## 2단계: Render에 배포 (5분)

1. [render.com](https://render.com) 가입 (GitHub 연동)
2. **New** → **Blueprint** (또는 **Web Service**)
3. 이 GitHub 저장소 연결
4. `render.yaml` 이 자동 인식되면 **Apply**
5. 배포 완료 후 URL 확인: `https://elliott-focused-viewer.onrender.com` (이름은 가변)

### Render 무료 플랜 참고

- 15분 미사용 시 슬립 → 첫 접속 시 30초~1분 대기 가능
- 분석 버튼은 기본 **비활성** (`DISABLE_SCAN=1`) — Actions가 데이터 갱신
- 수동 스캔을 웹에서 쓰려면 Render 환경변수에 `SCAN_SECRET=원하는비밀번호` 추가 후 `DISABLE_SCAN` 삭제

---

## 3단계: 커스텀 도메인 (선택)

Render 대시보드 → 서비스 → **Settings** → **Custom Domains**

예: `ew.yourdomain.com` CNAME 연결

---

## 다른 배포 옵션

### A. Railway / Fly.io

`지정종목_뷰어` 폴더를 루트로 지정하고:

```bash
pip install -r requirements-web.txt
gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 180
```

환경변수: `WEB_DEPLOY=1`, `MPLBACKEND=Agg`

### B. VPS (AWS Lightsail, Oracle Free Tier 등)

```bash
cd 지정종목_뷰어
pip install -r requirements-web.txt
WEB_DEPLOY=1 python app.py --server
```

또는 nginx + gunicorn + systemd로 상시 운영.

### C. PC + ngrok (이미 쓰던 방식)

로컬 서버를 터널로 공개. PC가 꺼지면 서비스 중단.

```bash
cd 지정종목_뷰어
python app.py --browser
# 다른 터미널
ngrok http 5789
```

---

## 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `PORT` | 5789 | 서버 포트 (Render가 자동 설정) |
| `WEB_DEPLOY` | - | 설정 시 프로덕션 모드 |
| `MPLBACKEND` | Agg | 서버에서 차트 생성용 |
| `DISABLE_SCAN` | - | `1`이면 웹에서 분석 버튼 숨김 |
| `SCAN_SECRET` | - | 설정 시 헤더 `X-Scan-Key` 필요 |

---

## 데이터 흐름

```
GitHub Actions (4h) ──► data/latest.json 커밋
                              │
Render 웹서버 ◄───────────────┘ (git pull / 재배포 시 반영)
       │
       ├── /api/latest  → JSON 결과
       └── /api/chart-b64/BTCUSDT → 실시간 차트 (Binance API)
```

Render는 **Auto-Deploy** 를 켜두면 Actions가 JSON을 커밋할 때마다 자동 재배포되어 최신 데이터가 반영됩니다.

---

## 문제 해결

| 증상 | 해결 |
|------|------|
| 빈 화면 | Actions에서 focused-scan 워크플로우 실행했는지 확인 |
| 차트 안 나옴 | `matplotlib` 설치 확인, 서버 로그에서 Binance API 오류 확인 |
| 분석 버튼 없음 | 의도된 동작. Actions 스케줄 사용 또는 `DISABLE_SCAN` 해제 |
| Render 느림 | 무료 슬립. 유료 플랜 또는 cron으로 10분마다 핑 (UptimeRobot 등) |

---

## 면책

투자 참고용 도구입니다. 실제 매매 결정은 본인 책임입니다.