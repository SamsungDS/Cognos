@echo off
REM =============================================================================
REM AMOprof — AI Memory & IO Profiler
REM Dependency installer for Windows
REM =============================================================================
REM Usage:
REM   install.bat            auto-detect Python
REM   install.bat --venv     install into a virtualenv
REM   install.bat --check    check only, no install
REM =============================================================================

setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
set "REQ_FILE=%SCRIPT_DIR%requirements.txt"
set "USE_VENV=0"
set "VENV_DIR=%SCRIPT_DIR%amoprof_env"
set "CHECK_ONLY=0"

REM ── parse args ───────────────────────────────────────────────────────────────
:parse_args
if "%~1"=="" goto find_python
if /i "%~1"=="--venv"  set "USE_VENV=1"  & shift & goto parse_args
if /i "%~1"=="--check" set "CHECK_ONLY=1" & shift & goto parse_args
shift & goto parse_args

REM ── find Python ──────────────────────────────────────────────────────────────
:find_python
echo.
echo ========================================
echo  AMOprof -- Dependency Installer
echo ========================================
echo.

set "PYTHON="
for %%P in (python3.12 python3.11 python3.10 python3 python) do (
    if "!PYTHON!"=="" (
        where %%P >nul 2>&1 && set "PYTHON=%%P"
    )
)

if "!PYTHON!"=="" (
    echo [ERROR] No Python interpreter found. Install Python ^>= 3.10 first.
    echo         Download: https://www.python.org/downloads/
    exit /b 1
)

for /f "tokens=*" %%V in ('!PYTHON! --version 2^>^&1') do set "PYVER=%%V"
echo [INFO]  Python: !PYVER!

REM ── check requirements file ──────────────────────────────────────────────────
if not exist "!REQ_FILE!" (
    echo [ERROR] requirements.txt not found at: !REQ_FILE!
    exit /b 1
)

REM ── check-only mode ──────────────────────────────────────────────────────────
if "!CHECK_ONLY!"=="1" (
    echo.
    echo -- Checking installed packages --
    !PYTHON! -c "
import sys
checks = ['matplotlib','numpy','pandas','openpyxl','requests','scipy','PIL']
missing = []
for pkg in checks:
    try:
        __import__(pkg)
        print(f'  OK     {pkg}')
    except ImportError:
        print(f'  MISSING  {pkg}')
        missing.append(pkg)
if missing:
    print(f'Missing: {missing}')
    sys.exit(1)
else:
    print('All dependencies satisfied.')
"
    exit /b !ERRORLEVEL!
)

REM ── virtualenv (optional) ────────────────────────────────────────────────────
if "!USE_VENV!"=="1" (
    echo.
    echo -- Setting up virtualenv: !VENV_DIR! --
    if not exist "!VENV_DIR!" (
        !PYTHON! -m venv "!VENV_DIR!"
        echo [OK]    Created virtualenv
    ) else (
        echo [INFO]  Virtualenv already exists
    )
    call "!VENV_DIR!\Scripts\activate.bat"
    set "PYTHON=python"
    echo [OK]    Virtualenv activated
)

REM ── upgrade pip ──────────────────────────────────────────────────────────────
echo.
echo -- Upgrading pip --
!PYTHON! -m pip install --quiet --upgrade pip
echo [OK]    pip upgraded

REM ── install ──────────────────────────────────────────────────────────────────
echo.
echo -- Installing AMOprof dependencies --
!PYTHON! -m pip install --quiet -r "!REQ_FILE!"
if !ERRORLEVEL! neq 0 (
    echo [WARN]  Standard install failed, trying --break-system-packages
    !PYTHON! -m pip install --quiet --break-system-packages -r "!REQ_FILE!"
)
echo [OK]    Dependencies installed

REM ── verify ───────────────────────────────────────────────────────────────────
echo.
echo -- Verifying imports --
!PYTHON! -c "
import sys
checks = [
    ('matplotlib', 'matplotlib'),
    ('numpy',      'numpy'),
    ('pandas',     'pandas'),
    ('openpyxl',   'openpyxl'),
    ('requests',   'requests'),
    ('scipy',      'scipy.stats'),
    ('Pillow',     'PIL.Image'),
]
ok_count = 0
for pkg, mod in checks:
    try:
        m = __import__(mod, fromlist=['__version__'])
        ver = getattr(m,'__version__','?')
        print(f'  OK  {pkg:<15} {ver}')
        ok_count += 1
    except Exception as e:
        print(f'  FAIL  {pkg:<15} {e}')
print(f'\n  {ok_count}/{len(checks)} imports OK')
sys.exit(0 if ok_count == len(checks) else 1)
"

echo.
echo ========================================
echo  AMOprof is ready to use!
echo ========================================
echo.
if "!USE_VENV!"=="1" echo   Activate env: !VENV_DIR!\Scripts\activate.bat
echo   Run: python amoprof.py --help
echo.
