# Elliott Wave Scanner

**바로 보기 → [https://elliott-focused-viewer-production.up.railway.app/](https://elliott-focused-viewer-production.up.railway.app/)**

바이낸스 USDT 거래량 상위 코인에서 엘리어트 파동 impulse(Wave 3 후보)를 찾아주는 스캐너입니다.  
4시간마다 자동 분석되고, 위 링크에서 최신 결과를 확인할 수 있습니다.

## 기능

- 거래량 상위 20종목 실시간 뷰어 (풀 스캔은 상위 100종목)
- 롱/숏 양방향 점수, 진입·손절·TP 레벨
- 최근 3일 1h 차트 + 레벨선·가격 패널
- GitHub Actions 자동 갱신 (`focused_viewer/data/latest.json`)

## 로컬에서 실행

```bash
cd focused_viewer
pip install -r requirements-web.txt
python app.py
```

→ `http://127.0.0.1:5789`

## 프로젝트 구조

| 폴더 | 역할 |
|------|------|
| `focused_viewer/` | 웹 뷰어 (Railway / Render 배포) |
| `elliott_wave_scanner.py` | 100종목 풀 스캔 |
| `results/` | 풀 스캔 결과 |
| `web/` | GitHub Pages용 간단 뷰어 |

배포 가이드: [`focused_viewer/DEPLOY.md`](focused_viewer/DEPLOY.md)

## 직접 배포하기

1. Fork 후 clone
2. Actions 권한: Settings → Actions → **Read and write permissions**
3. **Focused Coin Scan** 워크플로우 수동 실행
4. Railway 또는 Render에 `focused_viewer` 배포

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/JimProKing/elliott-wave-scanner)

## 참고

- Binance 공개 API만 사용 (API 키 불필요)
- 투자 조언이 아닌 참고용 도구입니다

문의 · [Issues](https://github.com/JimProKing/elliott-wave-scanner/issues) · 카카오톡 caramel112 · caramel2516@naver.com