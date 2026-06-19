@echo off
chcp 65001 >nul
title Elliott Wave Scanner - ngrok

echo ========================================
echo   Elliott Wave Scanner - ngrok public
echo ========================================
echo.

echo [1] Starting ngrok in background...
start /b ngrok http 5000

echo [2] Waiting for ngrok public URL (this may take 5-15 seconds)...
echo     Progress will be shown below.

set count=0
:waitloop
set /a count+=1
if %count% gtr 15 (
  echo.
  echo [ERROR] Failed to get ngrok public URL after waiting.
  echo Please check if ngrok is installed correctly.
  echo You can run "ngrok http 5000" in a separate window to get the link manually.
  echo Then run "python local_server.py" in this folder.
  goto end
)

timeout /t 2 >nul

set "NGROK_URL="
for /f "tokens=2 delims=," %%a in ('curl -s http://127.0.0.1:4040/api/tunnels 2^>nul ^| findstr "public_url"') do (
    set "NGROK_URL=%%a"
)

if not defined NGROK_URL (
  echo Still waiting... attempt %count% of 15
  goto waitloop
)

set "NGROK_URL=%NGROK_URL:"=%"
set "NGROK_URL=%NGROK_URL: =%"

echo.
echo ========================================
echo   EXTERNAL LINK (copy and share this URL):
echo ========================================
echo %NGROK_URL%
echo.
echo (Anyone with this link can access the site while your PC is on and this is running.)

echo.
echo Local access (same computer or local network):
echo   http://127.0.0.1:5000
echo.

echo [3] Starting the local web server...
echo     Keep this window open!
echo.

python local_server.py

:end
echo.
echo (The script has ended or encountered an issue.)
pause