@echo off
echo Starting DPA QA Test Manager...

:: 1. Start Backend (Port 9090)
echo Starting Backend...
start "DPA Backend" cmd /k "cd /d %~dp0backend && venv\Scripts\activate && python main.py"

:: 2. Start Frontend (Port 5190)
echo Starting Frontend...
start "DPA Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

:: 3. Wait a bit for servers to be ready
echo Waiting for servers to start...
timeout /t 5 /nobreak > nul

:: 4. Open Browser
echo Opening Browser...
start http://localhost:5190

echo System started! Keep the command windows open to keep the system running.
