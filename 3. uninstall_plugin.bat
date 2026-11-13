@echo off
REM ============================================================
REM  uninstall_plugin.bat - Quita el plugin de Civil 3D
REM  Uso para TESTING de desarrollo: garantiza que el proximo
REM  arranque de Civil 3D cargue un DLL "nuevo" y no una version
REM  vieja cacheada.
REM
REM  Borra:
REM   1. %APPDATA%\Autodesk\ApplicationPlugins\AsistenteC3D.bundle
REM      (donde lo deja build_plugin.bat / build_all.bat)
REM   2. %ProgramFiles%\Autodesk\ApplicationPlugins\AsistenteC3D.bundle
REM      (donde lo deja el instalador Inno Setup)
REM
REM  NO borra ni el exe de la app Python ni proyectos del usuario.
REM ============================================================
setlocal enabledelayedexpansion

set "USER_BUNDLE=%APPDATA%\Autodesk\ApplicationPlugins\AsistenteC3D.bundle"
set "PF_BUNDLE=%ProgramFiles%\Autodesk\ApplicationPlugins\AsistenteC3D.bundle"

echo.
echo =====================================================
echo  Asistente C3D - quitar plugin (dev / testing)
echo =====================================================

REM ---- Chequeo: Civil 3D corriendo bloquea los DLL ----
tasklist /FI "IMAGENAME eq acad.exe" 2>nul | find /I "acad.exe" >nul
if not errorlevel 1 (
    echo.
    echo [AVISO] Civil3D / AutoCAD esta corriendo ^(acad.exe^).
    echo         Si el plugin esta cargado, no se podra borrar el DLL.
    echo         Cierra Civil3D antes de continuar.
    echo.
    choice /C SN /M "Continuar de todas formas"
    if errorlevel 2 (
        echo Cancelado.
        pause
        exit /b 1
    )
)

set "REMOVED=0"

if exist "%USER_BUNDLE%" (
    echo.
    echo Borrando: %USER_BUNDLE%
    rmdir /s /q "%USER_BUNDLE%"
    if exist "%USER_BUNDLE%" (
        echo   [ERROR] No se pudo borrar ^(probablemente Civil3D lo tiene abierto^).
    ) else (
        echo   OK.
        set /a REMOVED=REMOVED+1
    )
) else (
    echo.
    echo ^(no habia bundle en %APPDATA%\Autodesk\ApplicationPlugins^)
)

if exist "%PF_BUNDLE%" (
    echo.
    echo Borrando: %PF_BUNDLE%
    REM Program Files exige admin: si no lo somos, pedimos elevacion via PowerShell.
    net session >nul 2>&1
    if errorlevel 1 (
        echo   Se necesita elevacion para borrar en Program Files.
        powershell -NoProfile -Command "Start-Process cmd -Verb RunAs -ArgumentList '/c rmdir /s /q ""%PF_BUNDLE%""'"
        timeout /t 2 >nul
    ) else (
        rmdir /s /q "%PF_BUNDLE%"
    )
    if exist "%PF_BUNDLE%" (
        echo   [ERROR] No se pudo borrar. Prueba corriendo este .bat como admin.
    ) else (
        echo   OK.
        set /a REMOVED=REMOVED+1
    )
) else (
    echo ^(no habia bundle en %ProgramFiles%\Autodesk\ApplicationPlugins^)
)

echo.
echo =====================================================
if "%REMOVED%"=="0" (
    echo  Nada que borrar: el plugin no estaba en ninguna ruta de autoload.
) else (
    echo  Listo — plugin quitado. Al abrir Civil3D no cargara nada del
    echo  Asistente C3D hasta que corras build_plugin.bat o instales de nuevo.
)
echo =====================================================
echo.
pause
endlocal
