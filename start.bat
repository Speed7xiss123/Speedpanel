@echo off
setlocal
chcp 65001 >nul
title SpeedPainel :: terminal

REM ----------------------------------------------------------------------
REM SpeedPainel :: bootstrap (Windows)
REM Usa o python do sistema. Cria .venv apenas se o usuario permitir
REM e se o antivirus nao bloquear.
REM ----------------------------------------------------------------------

set "USE_VENV=0"
if /I "%~1"=="--venv" set "USE_VENV=1"

if "%USE_VENV%"=="1" (
    if not exist ".venv\Scripts\python.exe" (
        echo [setup] criando venv...
        python -m venv .venv
        if errorlevel 1 (
            echo [aviso] venv bloqueado pelo AV. usando python do sistema.
            set "USE_VENV=0"
        )
    )
    if "%USE_VENV%"=="1" call ".venv\Scripts\activate.bat" 1>nul 2>nul
)

REM --- garante deps no python que sera usado ---
echo [setup] verificando dependencias...
python -c "import flask, requests" >nul 2>&1
if errorlevel 1 (
    echo [setup] instalando dependencias...
    python -m pip install --upgrade pip >nul 2>&1
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [erro] falha ao instalar dependencias
        pause
        exit /b 1
    )
) else (
    echo [ok] flask e requests ja disponiveis.
)

echo.
echo [run] iniciando servidor em http://localhost:5000
echo [info] CTRL+C para parar
echo.
python -m app.web
pause
