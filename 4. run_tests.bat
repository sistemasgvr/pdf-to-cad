@echo off
REM ============================================================
REM  run_tests.bat - Corre las pruebas de humo del proyecto.
REM  Rápidas y headless (no abren la interfaz). Uso: doble clic
REM  o desde consola en la raíz del proyecto.
REM ============================================================
setlocal
cd /d "%~dp0"

echo.
echo === Pruebas (pytest) ===
python -m pytest tests\ -q
set "RC=%errorlevel%"

echo.
if "%RC%"=="0" (
    echo [OK] Todas las pruebas pasaron.
) else (
    echo [ERROR] Fallaron pruebas ^(codigo %RC%^). Revisa el detalle arriba.
    echo Si es por falta de pytest:  pip install -r requirements.txt
)
echo.
pause
endlocal
