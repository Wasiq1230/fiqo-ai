@echo off
REM ═══════════════════════════════════════════════════════════
REM FIQO AI — One-click deploy script (Windows)
REM Run this from the project root folder (FiQO-ai/)
REM ═══════════════════════════════════════════════════════════

echo.
echo === FIQO AI — Deployment Script ===
echo.

REM ── Step 1: Check prerequisites ──────────────────────────
echo [1/7] Checking prerequisites...

where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo ERROR: Python not found. Install Python 3.12+
    pause
    exit /b 1
)

where node >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo ERROR: Node.js not found. Install Node.js 20+
    pause
    exit /b 1
)

python --version
node --version
echo OK

REM ── Step 2: Backend setup ────────────────────────────────
echo.
echo [2/7] Setting up backend...

cd backend

if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
)

echo Installing dependencies...
call venv\Scripts\activate.bat
pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo ERROR: pip install failed
    pause
    exit /b 1
)

if not exist .env (
    echo Creating .env from template...
    copy .env.example .env
    echo.
    echo *** IMPORTANT: Edit backend\.env and set your GROQ_API_KEY and SECRET_KEY ***
)

cd ..

REM ── Step 3: Run tests ────────────────────────────────────
echo.
echo [3/7] Running backend tests...
cd backend
call venv\Scripts\activate.bat
pytest -v
if %ERRORLEVEL% neq 0 (
    echo WARNING: Some tests failed. Check the output above.
) else (
    echo All tests passed!
)
cd ..

REM ── Step 4: Frontend setup ───────────────────────────────
echo.
echo [4/7] Setting up frontend...
cd frontend

if not exist node_modules (
    echo Installing dependencies...
    call npm install
)

cd ..

REM ── Step 5: Build frontend ───────────────────────────────
echo.
echo [5/7] Building frontend...
cd frontend
call npm run build
if %ERRORLEVEL% neq 0 (
    echo ERROR: Frontend build failed
    pause
    exit /b 1
)
echo Frontend built successfully!
cd ..

REM ── Step 6: Generate SECRET_KEY hint ─────────────────────
echo.
echo [6/7] SECRET_KEY generation...
python -c "import secrets; print('Generated SECRET_KEY:', secrets.token_urlsafe(48))"

REM ── Step 7: Summary ──────────────────────────────────────
echo.
echo ═══════════════════════════════════════════════════════════
echo DEPLOYMENT SETUP COMPLETE
echo ═══════════════════════════════════════════════════════════
echo.
echo NEXT STEPS:
echo.
echo 1. Edit backend\.env and set:
echo    - GROQ_API_KEY  (from console.groq.com/keys — rotate old key first!)
echo    - SECRET_KEY    (use the one generated above)
echo    - ENVIRONMENT=production
echo    - DEBUG=false
echo    - DATABASE_URL  (use Postgres, not SQLite)
echo    - CORS_ORIGINS  (your frontend domain)
echo    - ADMIN_EMAIL and ADMIN_PASSWORD
echo.
echo 2. Run the backend:
echo    cd backend
echo    venv\Scripts\activate
echo    gunicorn -k uvicorn.workers.UvicornWorker app.main:app -w 4
echo.
echo 3. Serve the frontend from: frontend\dist\
echo    (Upload to Vercel, Netlify, or any static host)
echo.
echo 4. Visit your frontend URL and log in with your admin credentials
echo.
echo ═══════════════════════════════════════════════════════════
pause
