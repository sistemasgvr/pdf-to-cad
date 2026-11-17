@echo off
REM ============================================================
REM  0. Tests instalador.bat - TODAS las pruebas antes de armar un instalador
REM  (pruebas de la app, cada archivo en su proceso, y el arnes del plugin C#).
REM  Tardan decenas de minutos: por eso van aparte de "1. build_all.bat"
REM  (pedido del usuario 2026-11-17). Correrlo antes de entregar un instalador.
REM  Informe: dist\informe_pruebas.md - salida de cada paso: dist\entrega\
REM  "1. build_all.bat" anota en su informe la ultima corrida de estas pruebas.
REM ============================================================
setlocal
cd /d "%~dp0"

REM Mismo Python que compila: el del .venv del proyecto si existe
set "PY=python"
if exist "%~dp0.venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"
echo Python para las pruebas: %PY%

echo.
echo ========================================
echo  Pruebas antes de armar el instalador
echo ========================================
"%PY%" scripts\verificar_entrega.py pruebas
set "RC=%errorlevel%"

echo.
if "%RC%"=="0" (
    echo [OK] Todas las pruebas pasaron. Ya puedes correr "1. build_all.bat".
) else (
    echo [ERROR] Fallaron pruebas. Revisa dist\informe_pruebas.md y dist\entrega\
)
echo.
pause
endlocal & exit /b %RC%
