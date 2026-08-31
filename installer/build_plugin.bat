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

REM Copia automática al autoload de Civil3D — Civil3D escanea esta carpeta al
REM arrancar (LoadOnAutoCADStartup="True" en PackageContents.xml) y carga el
REM plugin solo, sin NETLOAD manual. Si Civil3D está abierto con la versión
REM vieja cargada, el DLL de destino queda bloqueado (igual que bin\ durante
REM el desarrollo) — hay que cerrarlo y volver a correr este mismo comando.
set TARGET=%APPDATA%\Autodesk\ApplicationPlugins\AsistenteC3D.bundle
echo === Instalando en autoload de Civil3D: %TARGET% ===
robocopy "%BUNDLE%" "%TARGET%" /MIR /NFL /NDL /NJH >nul
set RC=%errorlevel%
if %RC% GEQ 8 (
    echo.
    echo ERROR: no se pudo copiar a %TARGET%.
    echo Si Civil3D esta abierto con una version anterior del plugin cargada,
    echo ciERRALO y vuelve a correr este comando — un DLL ya cargado no se
    echo puede reemplazar en caliente.
    endlocal
    exit /b 1
)

echo.
echo === Listo — el plugin ya autocarga en Civil3D, sin NETLOAD ===
echo (Re)abre Civil3D normalmente y los comandos ya van a estar disponibles.
endlocal
