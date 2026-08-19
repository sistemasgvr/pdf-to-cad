# diagnostico.ps1 - Recolecta el estado del plugin Asistente C3D en la maquina
# donde no carga el autoloader. Genera un reporte de texto para enviar al dev.
#
# Uso (PowerShell como administrador):
#   powershell -ExecutionPolicy Bypass -File diagnostico.ps1
#
# Genera: %USERPROFILE%\Desktop\AsistenteC3D_Diagnostico.txt

$ErrorActionPreference = "Continue"
$reporte = @()

function Sec($titulo) { $script:reporte += ""; $script:reporte += "======= $titulo ======="; $script:reporte += "" }
function Line($x) { $script:reporte += $x }

Line "AsistenteC3D - Diagnostico"
Line "Fecha: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Line "Maquina: $env:COMPUTERNAME  ·  Usuario: $env:USERNAME"
Line "OS: $((Get-CimInstance Win32_OperatingSystem).Caption) $((Get-CimInstance Win32_OperatingSystem).Version)"

# ---------------------------------------------------------------
Sec "1. Bundle instalado - Program Files"
$pfBundle = "C:\Program Files\Autodesk\ApplicationPlugins\AsistenteC3D.bundle"
if (Test-Path $pfBundle) {
    Line "EXISTE: $pfBundle"
    Get-ChildItem -Path $pfBundle -Recurse -File | ForEach-Object {
        $rel = $_.FullName.Substring($pfBundle.Length + 1)
        Line ("  {0,-50} {1,8} KB   Modif: {2}" -f $rel, [math]::Round($_.Length/1KB, 1), $_.LastWriteTime)
    }
} else {
    Line "NO EXISTE en Program Files. El instalador NO copio el bundle alli."
}

Sec "2. Bundle residual - AppData"
$appBundle = "$env:APPDATA\Autodesk\ApplicationPlugins\AsistenteC3D.bundle"
if (Test-Path $appBundle) {
    Line "EXISTE (residual): $appBundle"
    Line "Este bundle en AppData puede estar en conflicto con el de Program Files."
    Line "Solucion: borrar la carpeta $appBundle"
} else {
    Line "OK: no hay residual en AppData."
}

# ---------------------------------------------------------------
Sec "3. PackageContents.xml - contenido"
$xml = Join-Path $pfBundle "PackageContents.xml"
if (Test-Path $xml) {
    Line "Ruta: $xml"
    Get-Content $xml | ForEach-Object { Line "  $_" }
} else {
    Line "NO EXISTE. El bundle esta incompleto."
}

# ---------------------------------------------------------------
Sec "4. DLL principal - Zone.Identifier (bloqueo Windows)"
$dll = Join-Path $pfBundle "Contents\proyecto1.dll"
if (Test-Path $dll) {
    Line "Ruta: $dll"
    $fi = Get-Item $dll
    Line "Tamanio: $([math]::Round($fi.Length/1KB,1)) KB   Modif: $($fi.LastWriteTime)"
    $zone = Get-Item $dll -Stream Zone.Identifier -ErrorAction SilentlyContinue
    if ($zone) {
        Line "BLOQUEADO por Zone.Identifier (Windows lo marca downloaded-from-internet):"
        Get-Content $dll -Stream Zone.Identifier | ForEach-Object { Line "    $_" }
        Line "  Fix: Get-ChildItem '$pfBundle' -Recurse | Unblock-File"
    } else {
        Line "OK: sin Zone.Identifier."
    }
    $sig = Get-AuthenticodeSignature $dll
    Line "Firma: $($sig.Status)  Publisher: $($sig.SignerCertificate.Subject)"
} else {
    Line "NO EXISTE: $dll"
}

Sec "5. DLLs de Contents - status de bloqueo"
$contents = Join-Path $pfBundle "Contents"
if (Test-Path $contents) {
    Get-ChildItem $contents -File | ForEach-Object {
        $z = Get-Item $_.FullName -Stream Zone.Identifier -ErrorAction SilentlyContinue
        $mark = if ($z) { "BLOQUEADO" } else { "ok" }
        Line ("  {0,-50} {1}" -f $_.Name, $mark)
    }
} else {
    Line "No hay carpeta Contents."
}

# ---------------------------------------------------------------
Sec "6. .NET runtimes instalados en sistema"
try {
    $rt = & dotnet --list-runtimes 2>&1
    $rt | ForEach-Object { Line "  $_" }
} catch { Line "dotnet CLI no disponible (Civil 3D usa runtime bundleado, no afecta)." }

Sec "7. Civil 3D detectados en registro"
$c3dRoots = @("HKLM:\SOFTWARE\Autodesk\AutoCAD")
foreach ($root in $c3dRoots) {
    if (Test-Path $root) {
        Get-ChildItem $root | ForEach-Object {
            $rk = $_.PSChildName
            Get-ChildItem $_.PSPath -ErrorAction SilentlyContinue | ForEach-Object {
                $sk = $_.PSChildName
                $prod = (Get-ItemProperty $_.PSPath -Name "ProductName" -ErrorAction SilentlyContinue).ProductName
                $loc  = (Get-ItemProperty $_.PSPath -Name "AcadLocation" -ErrorAction SilentlyContinue).AcadLocation
                if ($prod) { Line ("  {0}\{1}   {2}   ({3})" -f $rk, $sk, $prod, $loc) }
            }
        }
    }
}

Sec "8. Sysvars relevantes (revisar en la linea de comandos de Civil 3D)"
Line "  SECURELOAD        (deberia ser 0, 1 o 2)"
Line "  APPAUTOLOAD       (deberia ser 14 = todo activo)"
Line "  TRUSTEDPATHS      (deberia incluir Program Files\Autodesk\ApplicationPlugins\...)"

# ---------------------------------------------------------------
Sec "9. Log de errores del Autoloader (si existe)"
$logDirs = @(
    "$env:LOCALAPPDATA\Autodesk\C3D 2027\enu",
    "$env:LOCALAPPDATA\Autodesk\C3D 2027",
    "$env:APPDATA\Autodesk\C3D 2027\enu",
    "$env:TEMP"
)
foreach ($d in $logDirs) {
    if (Test-Path $d) {
        $logs = @()
        $logs += Get-ChildItem $d -Filter "*autoload*" -Recurse -ErrorAction SilentlyContinue -File
        $logs += Get-ChildItem $d -Filter "*plugin*" -Recurse -ErrorAction SilentlyContinue -File
        foreach ($l in $logs) {
            Line "  $($l.FullName)   ($([math]::Round($l.Length/1KB,1)) KB, modif $($l.LastWriteTime))"
        }
    }
}

Sec "10. Marker del plugin - se ejecuto Initialize()?"
$markerDesk = Join-Path ([Environment]::GetFolderPath('Desktop')) "AsistenteC3D_ULTIMA_CARGA.txt"
$markerLog = Join-Path $env:LOCALAPPDATA "AsistenteC3D\carga_plugin.log"
if (Test-Path $markerDesk) {
    Line "SI: existe marker en Desktop:"
    Get-Content $markerDesk | ForEach-Object { Line "  $_" }
} else {
    Line "NO existe marker en Desktop. El Initialize() del plugin NO se ejecuto."
}
if (Test-Path $markerLog) {
    Line ""
    Line "Log de cargas historicas ($markerLog):"
    Get-Content $markerLog | Select-Object -Last 10 | ForEach-Object { Line "  $_" }
}

Sec "10b. PackageContents.xml de OTROS bundles que SI cargan (comparacion)"
$otherBundles = @(
    "C:\Program Files\Autodesk\ApplicationPlugins",
    "C:\Program Files (x86)\Autodesk\ApplicationPlugins"
)
foreach ($root in $otherBundles) {
    if (Test-Path $root) {
        Get-ChildItem $root -Directory -ErrorAction SilentlyContinue | ForEach-Object {
            if ($_.Name -ne "AsistenteC3D.bundle") {
                $otherXml = Join-Path $_.FullName "PackageContents.xml"
                if (Test-Path $otherXml) {
                    Line ""
                    Line ">>> $($_.Name)"
                    Get-Content $otherXml | Select-Object -First 40 | ForEach-Object { Line "  $_" }
                }
            }
        }
    }
}

Sec "11. Registro - Autoloader estado del bundle"
# Buscar ramas de Civil 3D 2027 (R26.0) y leer valores completos
$acadKeys = @()
if (Test-Path "HKCU:\Software\Autodesk\AutoCAD") {
    Get-ChildItem "HKCU:\Software\Autodesk\AutoCAD" -ErrorAction SilentlyContinue | ForEach-Object {
        Get-ChildItem $_.PSPath -ErrorAction SilentlyContinue | ForEach-Object {
            $acadKeys += $_.PSPath
        }
    }
}
foreach ($ak in $acadKeys) {
    Line ""
    Line ">>> $ak"
    # Applications (aqui autoCAD marca cada plugin cargado con LOADCTRLS)
    $apps = Join-Path $ak "Applications"
    if (Test-Path $apps) {
        Get-ChildItem $apps -ErrorAction SilentlyContinue | ForEach-Object {
            $name = $_.PSChildName
            $vals = Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue
            if ($name -match "Asistente|proyecto1|AsistenteC3D|Pdf") {
                Line "  Applications\$name :"
                $vals.PSObject.Properties | Where-Object { $_.Name -notmatch "^PS" } | ForEach-Object {
                    Line "    $($_.Name) = $($_.Value)"
                }
            }
        }
    }
    # InstalledApplications
    $inst = Join-Path $ak "InstalledApplications"
    if (Test-Path $inst) {
        Get-ChildItem $inst -ErrorAction SilentlyContinue | ForEach-Object {
            $name = $_.PSChildName
            if ($name -match "Asistente|proyecto1|AsistenteC3D") {
                Line "  InstalledApplications\$name :"
                Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue | ForEach-Object {
                    $_.PSObject.Properties | Where-Object { $_.Name -notmatch "^PS" } | ForEach-Object {
                        Line "    $($_.Name) = $($_.Value)"
                    }
                }
            }
        }
    }
    # Loaded (rama donde se registran los bundles vistos por autoloader)
    $loaded = Join-Path $ak "Loaded"
    if (Test-Path $loaded) {
        Get-ChildItem $loaded -ErrorAction SilentlyContinue | ForEach-Object {
            $name = $_.PSChildName
            if ($name -match "Asistente|AsistenteC3D") {
                Line "  Loaded\$name :"
                Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue | ForEach-Object {
                    $_.PSObject.Properties | Where-Object { $_.Name -notmatch "^PS" } | ForEach-Object {
                        Line "    $($_.Name) = $($_.Value)"
                    }
                }
            }
        }
    }
}

# ---------------------------------------------------------------
Sec "FIN"
Line "Enviar este archivo (Desktop\AsistenteC3D_Diagnostico.txt) al desarrollador."

$out = Join-Path $env:USERPROFILE "Desktop\AsistenteC3D_Diagnostico.txt"
$reporte | Out-File -FilePath $out -Encoding utf8
Write-Host ""
Write-Host "Reporte generado en:" -ForegroundColor Green
Write-Host "  $out" -ForegroundColor Yellow
Write-Host ""
Write-Host "Abrelo, revisa, y enviaselo al desarrollador."
