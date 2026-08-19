@echo off
REM build_plugin.bat — Publica el plugin y arma la carpeta .bundle lista para instalar.
REM Ejecutar desde la raíz del proyecto: installer\build_plugin.bat

setlocal
set PROJECT=API-CIVIL\proyecto1\proyecto1\proyecto1.csproj
set PUBDIR=installer\publish
set BUNDLE=installer\AsistenteC3D.bundle

echo === Publicando plugin (.NET 8 / x64) ===
dotnet publish "%PROJECT%" -c Release -r win-x64 --self-contained false -o "%PUBDIR%" /p:CopyLocalLockFileAssemblies=true
if errorlevel 1 (
    echo ERROR: dotnet publish fallo.
    exit /b 1
)

echo === Armando bundle ===
if exist "%BUNDLE%" rmdir /s /q "%BUNDLE%"
mkdir "%BUNDLE%\Contents"

copy /y "installer\PackageContents.xml" "%BUNDLE%\PackageContents.xml"
REM Copiar el script de diagnóstico junto al plugin para que el usuario final pueda ejecutarlo
if exist "installer\diagnostico.ps1" copy /y "installer\diagnostico.ps1" "%BUNDLE%\diagnostico.ps1" >nul

REM Copiar solo las DLLs necesarias (no las de Autodesk, ya las tiene Civil 3D)
for %%F in (
    proyecto1.dll
    proyecto1.deps.json
    ClosedXML.dll
    ClosedXML.Parser.dll
    DocumentFormat.OpenXml.dll
    DocumentFormat.OpenXml.Framework.dll
    ExcelNumberFormat.dll
    RBush.dll
    Serilog.dll
    Serilog.Sinks.File.dll
) do (
    if exist "%PUBDIR%\%%F" (
        copy /y "%PUBDIR%\%%F" "%BUNDLE%\Contents\%%F" >nul
        echo   + %%F
    ) else (
        echo   ? %%F no encontrado, omitido
    )
)

echo === Bundle listo: %BUNDLE% ===
echo Copiar la carpeta AsistenteC3D.bundle a:
echo   %%APPDATA%%\Autodesk\ApplicationPlugins\
endlocal
