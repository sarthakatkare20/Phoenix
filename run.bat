@echo off
title Phoenix - AI Assistant & Mission Control
echo ===================================================
echo           PHOENIX - STARTING MISSION CONTROL
echo ===================================================

echo [1/3] Starting Phoenix Python Voice Backend on Port 8000...
start "Phoenix Backend" cmd /k "python -m uvicorn server:app --host 127.0.0.1 --port 8000 --reload"

timeout /t 2 /nobreak >nul

echo [2/3] Starting Phoenix React 3D Face on Port 5173...
start "Phoenix Face" cmd /k "npm run dev"

timeout /t 2 /nobreak >nul

echo [3/3] Starting Phoenix Telegram Remote Gateway...
start "Phoenix Telegram" cmd /k "%LOCALAPPDATA%\hermes\bin\hermes.exe gateway run"

echo ===================================================
echo Phoenix is launching!
echo UI:       http://localhost:5173
echo API:      http://localhost:8000/docs
echo Telegram: @Phoenix_sarthak_bot (Online)
echo ===================================================
