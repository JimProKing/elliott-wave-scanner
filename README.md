# Elliott Wave Scanner

바이낸스 USDT 마켓 거래량 상위 코인을 대상으로, 엘리어트 파동 impulse(특히 Wave 3 후보)를 훑어보는 스캐너입니다.  
매일 차트 직접 돌려보면서 후보 찾기가 번거로워서 만들었고, 결과는 웹에서 바로 확인할 수 있게 해뒀습니다.

## 웹 뷰어

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/JimProKing/elliott-wave-scanner)

Render에 배포하면 `focused_viewer` 앱이 올라갑니다. 버튼 누르고 로그인한 뒤 **Apply** 한 번이면 끝입니다.  
배포 후 URL 예: `https://elliott-focused-viewer.onrender.com`

**하는 일**
- 거래량 상위 20종목 분석 (풀 스캐너는 상위 100종목)
- 롱/숏 양방향 점수, 진입·손절·TP 레벨
- 최근 3일 1h 차트에 레벨선 표시
- GitHub Actions가 4시간마다 분석 후 `focused_viewer/data/latest.json` 갱신

## 로컬 실행

```bash
cd focused_viewer
pip install -r requirements-web.txt
python app.py
```

브라우저에서 `http://127.0.0.1:5789` 로 접속합니다.

## 저장소 구성

| 경로 | 설명 |
|------|------|
| `focused_viewer/` | 웹 뷰어 (Flask) — Render 배포 대상 |
| `elliott_wave_scanner.py` | 거래량 상위 100종목 풀 스캔 |
| `results/` | 풀 스캔 결과 (`latest.json`, `latest.md`) |
| `web/` | GitHub Pages용 간단한 결과 뷰어 |

배포 상세는 [`focused_viewer/DEPLOY.md`](focused_viewer/DEPLOY.md) 참고.

## 직접 포크해서 쓰려면

1. 저장소 fork 또는 clone
2. GitHub Actions 권한: Settings → Actions → **Read and write permissions**
3. Actions 탭에서 **Focused Coin Scan** 워크플로우 수동 실행
4. `web/index.html`의 `GITHUB_USER`, `REPO`를 본인 계정으로 수정 (Pages 뷰어 쓸 때)
5. GitHub Pages 켜기 (Settings → Pages → GitHub Actions)

스캔 주기는 `.github/workflows/focused-scan.yml`의 cron, 종목 수는 `elliott_wave_scanner.py`의 `usdt_pairs[:100]`에서 조정할 수 있습니다.

## 참고

- 공개 Binance API만 사용합니다. API 키 필요 없음.
- 규칙 기반 휴리스틱 도구이며, 투자 조언이 아닙니다. 실제 매매 전에는 본인 차트 분석과 리스크 관리가 필요합니다.

문의: [GitHub Issues](https://github.com/JimProKing/elliott-wave-scanner/issues) · caramel112 (카카오톡) · caramel2516@naver.com