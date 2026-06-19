# GitHub + GitHub Actions + Public Website Setup Guide (Korean)

## 1. GitHub 저장소 준비

1. GitHub에서 새 **Public** 저장소를 만드세요 (예: `elliott-wave-scanner`).
2. 로컬에서 이 폴더 전체를 새 저장소로 push 하세요.

```bash
cd C:\Users\a\Documents\Trading\elliott-wave-scanner
git init
git add .
git commit -m "Initial commit - Elliott Wave Scanner + Web UI"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/elliott-wave-scanner.git
git push -u origin main
```

## 2. GitHub Actions 권한 설정 (중요)

Repo → Settings → Actions → General

- Workflow permissions → **Read and write permissions** 선택
- "Allow GitHub Actions to create and approve pull requests" 체크

## 3. GitHub Pages 활성화 (웹사이트 공개)

### 방법 A (가장 쉬움 - branch deploy)
- Settings → Pages
- Source: **Deploy from a branch**
- Branch: `main` / Folder: `/web`
- Save

접속 주소 예시:
`https://YOUR_USERNAME.github.io/elliott-wave-scanner/web/`

### 방법 B (GitHub Actions로 Pages 배포 - 더 현대적)
`.github/workflows/pages.yml` 파일을 추가하고 Pages source를 "GitHub Actions"로 바꾸세요 (필요하면 요청).

## 4. 웹사이트 설정 (필수)

`web/index.html` 파일을 열고 상단 두 줄을 수정하세요:

```js
const GITHUB_USER = "당신의_깃허브_아이디";
const REPO = "elliott-wave-scanner";
```

저장 후 push 하면 됩니다.

## 5. 첫 수동 실행

1. GitHub 저장소 페이지로 이동
2. 상단 **Actions** 탭 클릭
3. 왼쪽에서 "Elliott Wave Scan" 워크플로우 선택
4. 오른쪽 상단 **Run workflow** → 초록색 버튼 클릭

몇 분 후 `results/latest.json` 과 `results/latest.md` 가 업데이트됩니다.

웹사이트를 새로고침하면 결과가 나타납니다.

## 6. 자동 실행

이미 `.github/workflows/scan.yml` 에 4시간마다 자동 실행(cron)이 설정되어 있습니다.

## 문제 해결

- 결과가 안 보인다 → Actions 탭에서 워크플로우 실행 로그 확인
- 404 에러 → GitHub Pages 설정이 제대로 되었는지 확인
- 오래된 결과 → Actions가 아직 한 번도 안 돌았을 수 있음 (수동 실행 필수)

---

이제 누구나 인터넷에서 당신의 Elliott Wave 스캐너 결과를 실시간으로 볼 수 있습니다! 

추가로 궁금한 점 있으면 말씀해주세요.