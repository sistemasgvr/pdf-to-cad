@echo off
REM ============================================================
REM  build_all.bat - Un solo click: plugin C# + exe Python + instalador
REM  Uso: doble clic, o desde consola en la raiz del proyecto.
REM  Requisitos: Python (con venv o global) + dotnet SDK + Inno Setup 6.
REM ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

REM ---- 0) Version: leer la actual del .iss para ofrecerla como default ----
set "ISS=installer\setup.iss"
set "PKGXML=installer\PackageContents.xml"
set "CURVER=1.0.0"
for /f "tokens=3 delims= " %%A in ('findstr /R /C:"#define MyAppVersion" "%ISS%"') do (
    set "CURVER=%%~A"
    set "CURVER=!CURVER:"=!"
)

echo.
echo =====================================================
echo  Asistente C3D - build_all
echo =====================================================
echo Version actual detectada: %CURVER%
set /p "NEWVER=Nueva version (Enter = mantener %CURVER%): "
if "%NEWVER%"=="" set "NEWVER=%CURVER%"

REM Validacion basica: X.Y o X.Y.Z, solo digitos y puntos.
echo %NEWVER%| findstr /R /C:"^[0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*$" /C:"^[0-9][0-9]*\.[0-9][0-9]*$" >nul
if errorlevel 1 (
    echo [ERROR] Version invalida "%NEWVER%". Formato esperado: X.Y.Z o X.Y
    pause
    exit /b 1
)

echo Se compilara con version: %NEWVER%
echo.

REM ---- 1) Escribir la version en setup.iss y PackageContents.xml ----
REM Se escribe un .ps1 temporal (evita problemas de escapado y del "^" de cmd
REM cuando el interprete es PowerShell).
set "PS1TMP=%TEMP%\build_all_setver_%RANDOM%.ps1"
> "%PS1TMP%" echo $v = $args[0]
>> "%PS1TMP%" echo $iss = Get-Content -Raw $args[1]
>> "%PS1TMP%" echo $iss = [regex]::Replace($iss, '#define\s+MyAppVersion\s+"[^"]*"', '#define MyAppVersion "' + $v + '"')
>> "%PS1TMP%" echo Set-Content -Path $args[1] -Value $iss -NoNewline -Encoding UTF8
>> "%PS1TMP%" echo $pkg = Get-Content -Raw $args[2]
>> "%PS1TMP%" echo $pkg = [regex]::Replace($pkg, 'AppVersion="[^"]*"', 'AppVersion="' + $v + '"')
>> "%PS1TMP%" echo Set-Content -Path $args[2] -Value $pkg -NoNewline -Encoding UTF8
>> "%PS1TMP%" echo Write-Host ('  + Version escrita en setup.iss y PackageContents.xml: ' + $v)

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1TMP%" "%NEWVER%" "%ISS%" "%PKGXML%"
set "PSRC=%errorlevel%"
del /q "%PS1TMP%" 2>nul
if not "%PSRC%"=="0" (
    echo [ERROR] No se pudo actualizar la version en los archivos de instalador.
    pause
    exit /b 1
)

REM ---- Buscar ISCC.exe (Inno Setup) ----
set "ISCC="
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"

if "%ISCC%"=="" (
    echo [AVISO] No se encontro Inno Setup 6. Se compilaran plugin y exe pero
    echo         el instalador final NO se generara. Instalalo desde
    echo         https://jrsoftware.org/isdl.php y vuelve a correr esto.
    echo.
)

echo.
echo ========================================
echo  PASO 1/3: Compilar plugin C# (.NET 8)
echo ========================================
call installer\build_plugin.bat
set "PLG_RC=%errorlevel%"
REM Ojo: robocopy dentro del bat de plugin sale con 1..7 hasta cuando copia bien.
REM Se comprueba explicitamente contra 0 y no con "if errorlevel 1".
if not "%PLG_RC%"=="0" (
    echo.
    echo [ERROR] Fallo la compilacion del plugin C# ^(codigo %PLG_RC%^).
    pause
    exit /b 1
)

echo.
echo ========================================
echo  PASO 2/3: Crear ejecutable Python
echo ========================================
REM Limpiar dist previa (solo el exe, no el instalador si ya existe).
if exist "dist\Asistente C3D.exe" del /q "dist\Asistente C3D.exe" 2>nul
if exist build rmdir /s /q build 2>nul

python -m PyInstaller --clean -y PDF-a-CAD.spec
set "PYI_RC=%errorlevel%"
if not "%PYI_RC%"=="0" (
    echo.
    echo [ERROR] Fallo PyInstaller ^(codigo %PYI_RC%^). Verifica el venv y las dependencias.
    pause
    exit /b 1
)

if not exist "dist\Asistente C3D.exe" (
    echo.
    echo [ERROR] No se encontro "dist\Asistente C3D.exe" tras PyInstaller.
    pause
    exit /b 1
)

echo.
echo ========================================
echo  PASO 3/3: Generar instalador Inno Setup
echo ========================================
if "%ISCC%"=="" (
    echo [SALTADO] Inno Setup no instalado — el exe y el plugin quedaron listos
    echo           en dist\ e installer\AsistenteC3D.bundle\
    pause
    exit /b 0
)

"%ISCC%" "%ISS%"
set "ISCC_RC=%errorlevel%"
if not "%ISCC_RC%"=="0" (
    echo.
    echo [ERROR] Fallo Inno Setup ^(codigo %ISCC_RC%^).
    pause
    exit /b 1
)

set "OUTFILE=dist\AsistenteC3D-Setup-%NEWVER%.exe"

echo.
echo =====================================================
echo  LISTO!  Instalador generado:
echo    %OUTFILE%
echo =====================================================
echo.
if exist "%OUTFILE%" (
    REM Abrir la carpeta dist en el Explorador para que se vea el instalador.
    explorer "dist"
)
pause
endlocal
