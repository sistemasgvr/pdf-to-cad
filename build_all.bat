@echo off
REM ============================================================
REM  build_all.bat — One-shot: Python exe + C# DLL + Instalador
REM  Ejecutar desde la raíz del proyecto.
REM  Requisitos: Python venv activo, dotnet SDK, Inno Setup 6
REM ============================================================
setlocal

REM Buscar ISCC.exe
set "ISCC="
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"

echo.
echo ========================================
echo  PASO 1/3: Compilar plugin C# (.NET 8)
echo ========================================
call installer\build_plugin.bat
if errorlevel 1 (
    echo.
    echo [ERROR] Fallo la compilacion del plugin C#.
    pause
    exit /b 1
)

echo.
echo ========================================
echo  PASO 2/3: Crear ejecutable Python
echo ========================================
if exist dist\NUL rmdir /s /q dist 2>nul
python -m PyInstaller --clean -y PDF-a-CAD.spec
if errorlevel 1 (
    echo.
    echo [ERROR] Fallo PyInstaller.
    pause
    exit /b 1
)

if not exist "dist\Asistente C3D.exe" (
    echo.
    echo [ERROR] No se encontro "dist\Asistente C3D.exe"
    pause
    exit /b 1
)

echo.
echo ========================================
echo  PASO 3/3: Generar instalador Inno Setup
echo ========================================
if "%ISCC%"=="" (
    echo.
    echo [ERROR] No se encontro Inno Setup en ninguna ruta conocida.
    echo Instalar desde: https://jrsoftware.org/isdl.php
    pause
    exit /b 1
)

"%ISCC%" installer\setup.iss
if errorlevel 1 (
    echo.
    echo [ERROR] Fallo Inno Setup.
    pause
    exit /b 1
)

echo.
echo ========================================
echo  LISTO!
echo ========================================
echo Instalador generado en: dist\AsistenteC3D-Setup-1.0.0.exe
echo.
pause
