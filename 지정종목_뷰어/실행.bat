@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 지정종목 엘리어트 분석 뷰어 시작...
python -m pip install -r requirements.txt -q
python app.py
pause