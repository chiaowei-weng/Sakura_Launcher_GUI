@echo off
setlocal
set PYTHON=.\venv\Scripts\python.exe
if not exist %PYTHON% set PYTHON=python

if "%1"=="" goto help
if "%1"=="start" goto start
if "%1"=="stop" goto stop
if "%1"=="gui" goto gui
if "%1"=="status" goto status
if "%1"=="list" goto list

:start
echo 🚀 Starting Sakura Server and Taiwan Proxy (Preset: %2 or default)...
if "%2"=="" (
    %PYTHON% main.py --run-preset default
) else (
    %PYTHON% main.py --run-preset %2
)
echo 💡 Please connect your translator to port 8081 for Traditional Chinese.
goto end

:stop
echo 🛑 Stopping Sakura Server and Proxy...
taskkill /F /IM llama-server.exe /T 2>nul
wmic process where "commandline like '%%proxy.py%%'" delete 2>nul
if %errorlevel%==0 (
    echo ✅ Server and Proxy stopped.
) else (
    echo ℹ️ No running server found.
)
goto end

:gui
echo 🎨 Starting Sakura Launcher GUI...
start %PYTHON% main.py
goto end

:status
tasklist /FI "IMAGENAME eq llama-server.exe" | findstr llama-server.exe >nul
if %errorlevel%==0 (
    echo 🟢 Server is RUNNING.
) else (
    echo 🔴 Server is STOPPED.
)
goto end

:list
echo 📋 Available Presets:
%PYTHON% main.py --list-presets
goto end

:help
echo Sakura Launcher Manager
echo Usage: manage.bat [start ^| stop ^| gui ^| status ^| list] [preset_name]
goto end

:end
pause
