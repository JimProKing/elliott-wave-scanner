@echo off
chcp 65001 >nul
echo ========================================
echo  지정종목 엘리어트 뷰어 EXE 빌드
echo ========================================

cd /d "%~dp0"

python -m pip install -r requirements.txt

set BINANCE_DIR=%~dp0..\..\바이낸스
set ANALYZER=%BINANCE_DIR%\엘리어트_지정종목_분석.py
set UTILS=%BINANCE_DIR%\binance_utils.py

if not exist "%ANALYZER%" (
    echo [오류] 엘리어트_지정종목_분석.py 를 찾을 수 없습니다: %ANALYZER%
    pause
    exit /b 1
)

python -m PyInstaller ^
    --name "지정종목_엘리어트_뷰어" ^
    --onefile ^
    --windowed ^
    --add-data "templates;templates" ^
    --add-data "%ANALYZER%;바이낸스" ^
    --add-data "%UTILS%;바이낸스" ^
    --hidden-import "엘리어트_지정종목_분석" ^
    --hidden-import "binance_utils" ^
    --hidden-import "webview" ^
    --hidden-import "clr" ^
    --collect-all matplotlib ^
    --collect-all webview ^
    app.py

if %ERRORLEVEL% equ 0 (
    echo.
    echo ========================================
    echo  빌드 완료!
    echo  실행 파일: dist\지정종목_엘리어트_뷰어.exe
    echo ========================================
    echo.
    echo  주의: 분석 결과는 바이낸스\지정종목_엘리어트분석 폴더에 저장됩니다.
    echo  EXE는 Trading\바이낸스 폴더와 같은 위치에 두는 것을 권장합니다.
) else (
    echo [오류] 빌드 실패
)

pause