@echo off
REM ============================================================
REM  dev_build.bat - compila SOLO el plugin C# (DLL) en Release/x64.
REM  Fuerza recompilacion completa (Rebuild) para evitar el cache
REM  incremental de dotnet — asi el DLL SIEMPRE queda con la fecha
REM  actual y refleja el codigo que acabas de editar.
REM
REM  Salida: API-CIVIL\proyecto1\proyecto1\bin\x64\Release\proyecto1.dll
REM  Antes VS lo dejaba en bin\x64\Debug\proyecto1.dll (misma logica).
REM ============================================================
setlocal
cd /d "%~dp0"
set "START_TIME=%TIME%"

echo.
echo =====================================================
echo  dev_build - Rebuild plugin C# (Release, x64)
echo =====================================================
echo.

set "PROJECT=API-CIVIL\proyecto1\proyecto1\proyecto1.csproj"
set "BIN=API-CIVIL\proyecto1\proyecto1\bin"
set "OBJ=API-CIVIL\proyecto1\proyecto1\obj"
set "DLL=%BIN%\x64\Release\proyecto1.dll"

REM Borrar caches de compilacion para forzar rebuild real.
if exist "%BIN%" rmdir /s /q "%BIN%"
if exist "%OBJ%" rmdir /s /q "%OBJ%"

dotnet build "%PROJECT%" -c Release -p:Platform=x64 -t:Rebuild --nologo -v minimal
if errorlevel 1 (
    echo.
    echo [ERROR] Compilacion fallida. Revisa los errores arriba.
    pause
    exit /b 1
)

echo.
if exist "%DLL%" (
    for %%F in ("%DLL%") do (
        echo   DLL: %%~fF
        echo   Modificado: %%~tF
        echo   Tamano:     %%~zF bytes
    )
) else (
    echo   [WARN] No se encontro el DLL en %DLL%
    echo   Explora bin\ para ver donde quedo:
    dir /b /s "%BIN%\proyecto1.dll" 2>nul
)

echo.
echo =====================================================
echo  LISTO. Inicio: %START_TIME%   Fin: %TIME%
echo =====================================================
echo.
endlocal
exit /b 0
