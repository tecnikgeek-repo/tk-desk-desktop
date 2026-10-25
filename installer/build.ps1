# Crea <dist>\tk-desk-<ver>-windows.zip (aggiornamento), <dist>\tk-desk-<ver>-portatile.zip (cartella da estrarre)
# e <dist>\tk-desk-setup-<ver>.exe (installazione). Modello: tk-iscrizioni.
# Venv: .venv del progetto se c'è, altrimenti $env:TKDESK_VENV (predefinito C:\dev\venv-tkdesk).
# Dist: $env:TKDESK_DIST (predefinito C:\dev\tk-desk-dist), fuori da Dropbox: i pacchetti pesano.
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$version = (Select-String -Path 'tkdesk\__init__.py' -Pattern 'VERSION = "(.+)"').Matches[0].Groups[1].Value
$stageRoot = Join-Path $env:TEMP 'tkdesk-stage'
$stage = Join-Path $stageRoot 'app'
$dist = if ($env:TKDESK_DIST) { $env:TKDESK_DIST } else { 'C:\dev\tk-desk-dist' }
$venv = if (Test-Path (Join-Path $root '.venv')) { Join-Path $root '.venv' } elseif ($env:TKDESK_VENV) { $env:TKDESK_VENV } else { 'C:\dev\venv-tkdesk' }
Write-Host "== tk-desk ${version} (venv $venv)"
if (Test-Path $stageRoot) { Remove-Item $stageRoot -Recurse -Force }
New-Item -ItemType Directory -Force $stage | Out-Null
New-Item -ItemType Directory -Force $dist | Out-Null

function Robo($src, $dst, [string[]]$extra) {
    & robocopy $src $dst /E /NFL /NDL /NJH /NJS /NP @extra | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy fallito ($LASTEXITCODE): $src" }
}

# icona
& "$venv\Scripts\python.exe" tools_make_icon.py | Out-Null
if (-not (Test-Path 'assets\tk-desk.ico')) { throw 'Icona non generata' }

# Python ridotto (senza tkinter, test, pip...) + le librerie di tk-desk + solo le parti di PySide6 che servono
$homeLine = Get-Content "$venv\pyvenv.cfg" | Where-Object { $_ -match '^home\s*=' }
$pyHome = ($homeLine -replace '^home\s*=\s*', '').Trim()
$py = Join-Path $stage 'python'
Robo $pyHome $py @('/XD', 'test', 'tests', 'idlelib', 'tkinter', 'turtledemo', 'tcl', 'include', 'libs', 'Scripts',
                   'ensurepip', 'lib2to3', 'site-packages', '__phello__', 'pydoc_data',
                   '/XF', '*.pdb', '_tkinter.pyd', 'tcl*.dll', 'tk*.dll', 'EXTERNALLY-MANAGED')
$sp = "$venv\Lib\site-packages"
$dsp = Join-Path $py 'Lib\site-packages'
New-Item -ItemType Directory -Force $dsp | Out-Null
# WebRTC (aiortc e quello che si porta dietro), cattura dello schermo, mouse e tastiera, certificati
$pacchetti = @('shiboken6', 'certifi', 'aiortc', 'aioice', 'av', 'av.libs', 'cryptography', 'OpenSSL', 'cffi',
               'pycparser', 'pylibsrtp', 'google_crc32c', 'pyee', 'ifaddr', 'dns', 'numpy', 'numpy.libs', 'mss', 'pynput',
               '_sounddevice_data')
foreach ($p in $pacchetti) {
    if (-not (Test-Path "$sp\$p")) { throw "Libreria mancante nel venv: $p" }
    Robo "$sp\$p" "$dsp\$p" @('/XD', '__pycache__', 'tests', 'testing')
}
foreach ($f in @('_cffi_backend.cp313-win_amd64.pyd', 'six.py', 'typing_extensions.py', 'sounddevice.py', '_sounddevice.py')) {
    Get-ChildItem $sp -File -Filter $f | ForEach-Object { Copy-Item $_.FullName $dsp }
}
# i metadati (alcune librerie leggono la propria versione con importlib.metadata)
$meta = @('shiboken6', 'pyside6', 'certifi', 'aiortc', 'aioice', 'av', 'cryptography', 'pyopenssl', 'cffi', 'pycparser',
          'pylibsrtp', 'google_crc32c', 'pyee', 'ifaddr', 'dnspython', 'numpy', 'mss', 'pynput', 'six', 'typing_extensions',
          'sounddevice')
Get-ChildItem $sp -Directory -Filter '*.dist-info' | Where-Object { $meta -contains (($_.Name -split '-')[0].ToLower()) } |
    ForEach-Object { Robo $_.FullName "$dsp\$($_.Name)" @() }
$ps = "$sp\PySide6"
$dps = "$dsp\PySide6"
New-Item -ItemType Directory -Force $dps | Out-Null
$files = @('pyside6.abi3.dll', 'QtCore.pyd', 'QtGui.pyd', 'QtWidgets.pyd', 'Qt6Core.dll', 'Qt6Gui.dll', 'Qt6Widgets.dll',
           'Qt6Svg.dll')
Get-ChildItem $ps -File | Where-Object {
    $_.Extension -eq '.py' -or $files -contains $_.Name -or $_.Name -match '^(msvcp140|vcruntime140|concrt140)'
} | ForEach-Object { Copy-Item $_.FullName $dps }
foreach ($plug in @('platforms\qwindows.dll', 'platforms\qoffscreen.dll', 'styles\qmodernwindowsstyle.dll',
                    'iconengines\qsvgicon.dll', 'imageformats\qjpeg.dll', 'imageformats\qico.dll', 'imageformats\qsvg.dll')) {
    $srcp = Join-Path "$ps\plugins" $plug
    if (Test-Path $srcp) {
        $dstp = Join-Path "$dps\plugins" $plug
        New-Item -ItemType Directory -Force (Split-Path $dstp) | Out-Null
        Copy-Item $srcp $dstp
    }
}
New-Item -ItemType Directory -Force "$dps\translations" | Out-Null
Copy-Item "$ps\translations\qtbase_it.qm" "$dps\translations\" -ErrorAction SilentlyContinue

Robo 'tkdesk' "$stage\tkdesk" @('/XD', '__pycache__')
New-Item -ItemType Directory -Force "$stage\assets" | Out-Null
Copy-Item 'assets\tk-desk.ico' "$stage\assets\"
Copy-Item 'run.py' $stage
# testi delle licenze accanto a run.py: AGPL di tk-desk, licenze dei componenti inclusi (dai *.dist-info) e COMPONENTI.txt
$env:PYTHONIOENCODING = 'utf-8'
& "$venv\Scripts\python.exe" tools_licenze.py "$stage\licenze"
if ($LASTEXITCODE -ne 0 -or -not (Test-Path "$stage\licenze\COPYING-AGPL-3.0.txt") -or -not (Test-Path "$stage\licenze\COMPONENTI.txt")) {
    throw 'Cartella licenze non creata'
}
& "$py\python.exe" -m compileall -q "$py\Lib" 2>$null | Out-Null
# il codice di tk-desk va nel pacchetto SOLO compilato: .pyc accanto ai moduli (-b), sorgenti tolti
& "$py\python.exe" -m compileall -q -b "$stage\tkdesk" 2>$null | Out-Null
Get-ChildItem "$stage\tkdesk" -Recurse -File -Filter '*.py' | Remove-Item -Force
Get-ChildItem "$stage\tkdesk" -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force
if (Get-ChildItem "$stage\tkdesk" -Recurse -File -Filter '*.py') { throw 'Nel pacchetto sono rimasti dei sorgenti .py' }

# verifica 1: prove del motore con il Python del pacchetto (due tk-desk in locale, sessione WebRTC vera)
Robo 'tests' "$stage\tests" @('/XD', '__pycache__', '/XF', '*.png', '*.txt', '*.csv')
$env:PYTHONIOENCODING = 'utf-8'
$env:QT_QPA_FONTDIR = "$env:WINDIR\Fonts"  # PySide6 ridotto: senza, Qt scrive un avviso su stderr e PS5 lo prende per errore
$ErrorActionPreference = 'Continue'  # gli avvisi di Qt su stderr non sono errori
$out = & "$py\python.exe" "$stage\tests\test_core.py" 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) { throw "Prove del motore fallite:`n$out" }
Write-Host "   prove del motore OK (WebRTC, conferma locale, password che cambia, comandi, file, appunti, registrazione, accesso non presidiato)"
$out = & "$py\python.exe" "$stage\tests\test_finestre.py" 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) { throw "Prove delle finestre fallite:`n$out" }
Write-Host "   prove delle finestre OK (benvenuto, licenze, informazioni, impostazioni, Accetta/Rifiuta)"
$ErrorActionPreference = 'Stop'
Remove-Item "$stage\tests" -Recurse -Force
Remove-Item "$py\python.exe"

# verifica 2: avvio reale dal runtime ridotto (finestra principale + sessione con schermo di prova)
$shot = Join-Path $stageRoot 'selftest.png'
$p = Start-Process "$py\pythonw.exe" -ArgumentList "`"$stage\run.py`"", '--selftest', "`"$shot`"" -PassThru
if (-not $p.WaitForExit(90000)) { Stop-Process -Id $p.Id -Force; throw 'Selftest in timeout' }
if (-not (Test-Path $shot) -or -not (Test-Path "$stageRoot\selftest.txt")) { throw 'Selftest fallito: il pacchetto non avvia tk-desk o la sessione non arriva' }
Copy-Item $shot (Join-Path $dist "selftest-$version.png") -Force
Remove-Item $shot, "$stageRoot\selftest.txt"
Write-Host "   selftest del pacchetto OK (finestra + sessione con video)"
Get-ChildItem $stage -Recurse -Directory -Filter 'Dati' | Remove-Item -Recurse -Force

$zipCode = "import os,sys,zipfile`nsrc,dst=sys.argv[1],sys.argv[2]`nwith zipfile.ZipFile(dst,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:`n  for d,_,fs in os.walk(src):`n    for f in fs:`n      p=os.path.join(d,f); z.write(p, os.path.relpath(p,src).replace(os.sep,'/'))"
$updateZip = Join-Path $dist "tk-desk-$version-windows.zip"
& "$pyHome\python.exe" -c $zipCode $stage $updateZip
if ($LASTEXITCODE -ne 0) { throw 'ZIP aggiornamento fallito' }
# nello ZIP devono esserci le licenze e le librerie comuni (licenza, verifica della firma degli aggiornamenti)
$checkCode = "import sys,zipfile`nn=set(zipfile.ZipFile(sys.argv[1]).namelist())`nm=[x for x in ('licenze/COPYING-AGPL-3.0.txt','licenze/COMPONENTI.txt','licenze/LGPL-3.0.txt','tkdesk/tk_licenza.pyc','tkdesk/tk_licenza_qt.pyc','tkdesk/tk_aggiornamento.pyc') if x not in n]`nprint('mancano: '+', '.join(m) if m else 'ok')`nsys.exit(1 if m else 0)"
$check = & "$pyHome\python.exe" -c $checkCode $updateZip
if ($LASTEXITCODE -ne 0) { throw "ZIP incompleto: $check" }
Write-Host "   ZIP con licenze e librerie comuni: $check"

$pack = Join-Path $stageRoot "pack\tk-desk-$version"
New-Item -ItemType Directory -Force "$pack\Dati" | Out-Null
Set-Content -Path "$pack\Dati\.tieni" -Value '' -Encoding ASCII
Robo $stage "$pack\app" @()
$cmd = Get-Content "$PSScriptRoot\Avvia tk-desk.cmd" -Raw
[IO.File]::WriteAllText("$pack\Avvia tk-desk.cmd", ($cmd -replace "`r?`n", "`r`n"), [Text.Encoding]::ASCII)
$readme = Get-Content "$PSScriptRoot\Leggimi.txt" -Raw -Encoding UTF8
[IO.File]::WriteAllText("$pack\Leggimi.txt", ($readme -replace "`r?`n", "`r`n"), (New-Object Text.UTF8Encoding($true)))
$portZip = Join-Path $dist "tk-desk-$version-portatile.zip"
& "$pyHome\python.exe" -c $zipCode (Join-Path $stageRoot 'pack') $portZip
if ($LASTEXITCODE -ne 0) { throw 'ZIP portatile fallito' }
# --- installer exe (stesso modello di tk-pdf: setup.cs = strumenti\tk-setup.cs); contiene il pacchetto di aggiornamento
$csc = "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
$sizeKb = [int]((Get-ChildItem $stage -Recurse -File | Measure-Object Length -Sum).Sum / 1KB)
$map = [ordered]@{
    NAME = 'tk-desk'
    SLUG = 'tk-desk'
    TAGLINE = 'controllo remoto e assistenza'
    SUBDIR = 'app'
    DATADIR = 'Dati'
    ICON = 'tk-desk.ico'
    ACCENT = '#059669'
    UNINSTALL = 'cmd'
    UNINSTALLKEY = 'tk-desk'
    LNK = 'tk-desk'
    LEGACYLNK = ''
    LAUNCHSCHEMA = ''
    ITEMS = ''
    VERSION = $version
    SIZEKB = "$sizeKb"
}
$setupSrc = Get-Content "$PSScriptRoot\setup.cs" -Raw -Encoding UTF8
foreach ($k in $map.Keys) { $setupSrc = $setupSrc.Replace("@@$k@@", [string]$map[$k]) }
$genSrc = Join-Path $stageRoot 'setup.cs'
[IO.File]::WriteAllText($genSrc, $setupSrc, (New-Object Text.UTF8Encoding($true)))
$setupExe = Join-Path $dist "tk-desk-setup-$version.exe"
& $csc /nologo /optimize+ /target:winexe /platform:anycpu /win32icon:"$root\assets\tk-desk.ico" `
    /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:System.Core.dll `
    /reference:System.IO.Compression.dll /reference:System.IO.Compression.FileSystem.dll `
    /resource:"$updateZip",payload.zip /out:"$setupExe" $genSrc
if ($LASTEXITCODE -ne 0) { throw 'Compilazione installer fallita' }
Write-Host "   installer: $setupExe ($([math]::Round((Get-Item $setupExe).Length/1MB,1)) MB)"

$sha = (Get-FileHash $updateZip -Algorithm SHA256).Hash.ToLower()
Write-Host "== Creati:`n   $portZip ($([math]::Round((Get-Item $portZip).Length/1MB,1)) MB)`n   $updateZip`n   sha256 aggiornamento: $sha"
Remove-Item $stageRoot -Recurse -Force
