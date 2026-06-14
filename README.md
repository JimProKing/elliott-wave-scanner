# Elliott Wave Scanner + Public Web UI

주문량 상위 100개 USDT 페어 대상으로 Elliott Wave 상승 impulse (Wave 3 후보)를 스캔하는 도구입니다.

** 특징 **
- GitHub Actions로 자동 실행 (4시간마다)
- 결과를 `results/latest.json` + `latest.md` 로 커밋
- GitHub Pages로 외부에서 바로 볼 수 있는 웹사이트 제공
- "Run" 버튼으로 수동 실행 트리거 가능

## 빠른 시작 (GitHub에 올리는 방법)

1. **새 저장소 만들기**
   - GitHub에서 새 public repo 생성 (이름 추천: `elliott-wave-scanner`)

2. **파일 업로드**
   ```bash
   git clone https://github.com/YOUR_USERNAME/elliott-wave-scanner.git
   cd elliott-wave-scanner

   # 이 폴더의 모든 파일 복사 (또는 아래 파일들 추가)
   ```

3. **필요한 파일들**
   - `elliott_wave_scanner.py`
   - `.github/workflows/scan.yml`
   - `web/index.html`
   - `README.md`

4. **GitHub Pages 활성화**
   - Repo → Settings → Pages
   - Source: **GitHub Actions** (또는 `/web` 폴더를 `docs`로 이동해서 Deploy from a branch 선택)

5. **웹사이트 수정**
   - `web/index.html` 파일에서 상단 두 줄 수정:
     ```js
     const GITHUB_USER = "당신의_깃허브_아이디";
     const REPO = "elliott-wave-scanner";
     ```

6. **첨 실행**
   - Actions 탭 → "Elliott Wave Scan" 워크플로우 → **Run workflow** 클릭

## 웹사이트 사용법

- https://YOUR_USERNAME.github.io/elliott-wave-scanner/ (또는 `web` 폴더를 배포한 경우)
- 페이지에 최신 결과가 자동 표시됩니다.
- "Run Scan (GitHub)" 버튼을 누르면 GitHub Actions 페이지로 이동 → Run workflow로 수동 실행 가능.

## 커스터마이징

- 스켄 주기 변경: `.github/workflows/scan.yml`의 cron 수정
- 볼륨 푸 크기 변경: `elliott_wave_scanner.py`의 `usdt_pairs[:100]`
- 결과 형식 변경: `latest.json` 구조 수정

## 참고

- 이 스캐너는 **공개 Binance API**만 사용합니다 (API 키 불필요).
- 전문 투자 참고용이며, 실제 매매 전 반드시 본인 차트 분석을 하세요.

---

이제 GitHub에 올리고 Pages를 켜면 누구나 외부에서 최신 Elliott Wave 스캔 결과를 볼 수 있습니다! 