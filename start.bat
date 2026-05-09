@echo off
echo Starting PRISM...
start "PRISM API" cmd /k "cd /d %~dp0apps\api && uvicorn prism.main:app --reload --port 8000"
start "PRISM Web" cmd /k "cd /d %~dp0apps\web && pnpm dev"
echo.
echo API  -> http://localhost:8000
echo Web  -> http://localhost:3000
echo Docs -> http://localhost:8000/api/docs
