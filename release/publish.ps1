# Pubblica una versione di tk-desk per Windows, Mac e Linux: gli utenti la ricevono con l'aggiornamento automatico.
# Uso:  powershell -ExecutionPolicy Bypass -File release\publish.ps1 -Notes "Novita 1|Novita 2" [-SoloWindows]
# Prima: VERSION alzata in tkdesk\__init__.py e commit fatto (lo script fa push e attende le build Mac e Linux su GitHub).
# -SoloWindows: solo se le build su GitHub sono bloccate (il manifest esce senza le chiavi mac-* e linux-*;
#   le cartelle Mac\ e Linux\ di Dropbox non si toccano).
param(
    [Parameter(Mandatory = $true)][string]$Notes,
    [switch]$SoloWindows
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

$noteList = New-Object System.Collections.ArrayList
foreach ($n in ($Notes -split '\|')) { if ($n.Trim()) { [void]$noteList.Add($n.Trim()) } }
$version = (Select-String -Path 'tkdesk\__init__.py' -Pattern 'VERSION = "(.+)"').Matches[0].Groups[1].Value
$repo = 'tecnikgeek-repo/tk-desk-desktop'
$sshConfig = "$env:USERPROFILE\Dropbox\CLAUDE\fleet\ssh-config"
$remoteDir = 'public_html/updates/tk-desk'
$baseUrl = 'https://pietrodefilippis.it/updates/tk-desk'
$dropbox = "$env:USERPROFILE\Dropbox\CLAUDE\tk-software\tk-desk"
Write-Host "== Pubblicazione tk-desk $version (Windows + Mac + Linux)"

try {
    $current = Invoke-RestMethod "https://pietrodefilippis.it/updates/tk-desk.json?t=$([DateTime]::Now.Ticks)" -TimeoutSec 15
    if ([version]$current.version -ge [version]$version) {
        throw "Sul server c'e' gia' la versione $($current.version): alza VERSION in tkdesk\__init__.py"
    }
} catch [System.Net.WebException] { Write-Host "   nessun manifest precedente" }

# --- Windows
$dist = if ($env:TKDESK_DIST) { $env:TKDESK_DIST } else { 'C:\dev\tk-desk-dist' }
$winZip = "$dist\tk-desk-$version-windows.zip"
$winPortable = "$dist\tk-desk-$version-portatile.zip"
if (-not (Test-Path $winZip) -or -not (Test-Path $winPortable)) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File installer\build.ps1
    if ($LASTEXITCODE -ne 0) { throw 'Build Windows fallita' }
}
$assets = @(@{ key = 'windows-zip'; file = (Resolve-Path $winZip).Path })
# installazione .exe: e' il download «Windows» della vetrina (pietrodefilippis.it/scarica-programma/...)
$setupWin = "$dist\tk-desk-setup-$version.exe"
if (-not (Test-Path $setupWin)) { throw "Manca l'installazione ${setupWin}: rifai installer\build.ps1" }
$assets += @{ key = 'windows'; file = (Resolve-Path $setupWin).Path }

# --- Mac e Linux: build su GitHub del commit corrente, dmg e AppImage presi dalla release v<versione>
if (git status --porcelain --untracked-files=no) { throw 'Ci sono modifiche non committate: fai commit prima di pubblicare' }
git push -q
# tag della versione: e' il link "codice sorgente" del programma (URL_SORGENTE = .../tree/v<versione>)
if (-not (git tag --list "v$version")) { git tag "v$version" }
git push -q origin "v$version"
if ($LASTEXITCODE -ne 0) { throw "Push del tag v$version non riuscito" }
if (-not $SoloWindows) {
    # le build Mac e Linux non partono da sole a ogni push: le avvio io, in parallelo, sul commit appena inviato
    $sha = (git rev-parse HEAD).Trim()
    $runs = @{}
    foreach ($wf in 'build-mac.yml', 'build-linux.yml') {
        gh workflow run $wf --repo $repo --ref main
        if ($LASTEXITCODE -ne 0) { throw "Avvio di $wf su GitHub non riuscito" }
    }
    Start-Sleep -Seconds 5
    foreach ($wf in 'build-mac.yml', 'build-linux.yml') {
        $runId = $null
        for ($i = 0; $i -lt 30 -and -not $runId; $i++) {
            $runId = gh run list --repo $repo --workflow $wf --commit $sha --json databaseId --jq '.[0].databaseId'
            if (-not $runId) { Start-Sleep -Seconds 5 }
        }
        if (-not $runId) { throw "$wf non trovata su GitHub" }
        $runs[$wf] = $runId
    }
    Write-Host "   attendo le build macOS e Linux del commit $($sha.Substring(0,7))"
    foreach ($wf in $runs.Keys) {
        gh run watch $runs[$wf] --repo $repo --exit-status | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "$wf fallita: https://github.com/$repo/actions/runs/$($runs[$wf]) (per pubblicare solo Windows: -SoloWindows)" }
    }
    $macDir = "$dist\mac-$version"
    if (Test-Path $macDir) { Remove-Item -LiteralPath $macDir -Recurse -Force }
    New-Item -ItemType Directory -Force $macDir | Out-Null
    gh release download "v$version" --repo $repo --dir $macDir --pattern '*.dmg'
    if ($LASTEXITCODE -ne 0) { throw "Download dei dmg dalla release v$version fallito" }
    foreach ($arch in 'arm64', 'x86_64') {
        $dmg = Join-Path $macDir "tk-desk-$version-mac-$arch.dmg"
        if (-not (Test-Path $dmg)) { throw "Manca il dmg $arch" }
        $assets += @{ key = "mac-$arch"; file = (Resolve-Path $dmg).Path }
    }
    gh release download "v$version" --repo $repo --dir $macDir --pattern '*.AppImage' --clobber
    if ($LASTEXITCODE -ne 0) { throw "Download dell'AppImage dalla release v$version fallito" }
    $appImage = Join-Path $macDir "tk-desk-$version-linux-x86_64.AppImage"
    if (-not (Test-Path $appImage)) { throw "Manca l'AppImage Linux" }
    $assets += @{ key = 'linux-x86_64'; file = (Resolve-Path $appImage).Path }
}

# --- manifest
$manifest = [ordered]@{ name = 'tk-desk'; version = $version; date = (Get-Date -Format 'dd/MM/yyyy'); notes = $noteList }
foreach ($a in $assets) {
    $name = Split-Path $a.file -Leaf
    $manifest[$a.key] = [ordered]@{
        url    = "$baseUrl/$name"
        sha256 = (Get-FileHash $a.file -Algorithm SHA256).Hash.ToLower()
        size   = (Get-Item $a.file).Length
    }
}
$manifestFile = Join-Path $env:TEMP 'tk-desk.json'
[IO.File]::WriteAllText($manifestFile, ($manifest | ConvertTo-Json -Depth 5), (New-Object Text.UTF8Encoding($false)))
# firma (Ed25519) di ogni file del manifest, dopo l'ultima modifica e prima dell'upload: dalla 1.1.0 tk-desk
# installa solo aggiornamenti firmati. Lo slug e' il nome del file del manifest (updater.SLUG = tk-desk).
python -I "C:\Users\TecnikGeek\Dropbox\CLAUDE\tk-software\librerie\firma_aggiornamenti.py" firma --slug tk-desk $manifestFile
if ($LASTEXITCODE -ne 0) { throw 'Firma del manifest non riuscita: niente pubblicazione' }

# --- upload: prima i file, per ultimo il manifest
Write-Host "   caricamento sul server"
ssh -F $sshConfig pietrodefilippis "mkdir -p ~/$remoteDir/old"
# il portatile NON va sul server (niente download pubblico, Pietro 2026-10-11): solo Dropbox
$uploads = @($assets | ForEach-Object { $_.file })
foreach ($f in $uploads) {
    scp -q -F $sshConfig $f "pietrodefilippis:~/$remoteDir/"
    if ($LASTEXITCODE -ne 0) { throw "Upload fallito: $f" }
}
scp -q -F $sshConfig $manifestFile "pietrodefilippis:~/public_html/updates/tk-desk.json.new"
$names = ($uploads | ForEach-Object { Split-Path $_ -Leaf }) -join ' '
$remote = @'
cd ~/__DIR__ && rm -f old/* && for f in tk-desk-*; do keep=0; for k in __NAMES__; do [ "$f" = "$k" ] && keep=1; done; [ $keep = 1 ] || mv -f "$f" old/; done && mv -f ~/public_html/updates/tk-desk.json.new ~/public_html/updates/tk-desk.json && ls ~/__DIR__
'@
$remote = $remote.Replace('__DIR__', $remoteDir).Replace('__NAMES__', $names).Trim()
ssh -F $sshConfig pietrodefilippis $remote
if ($LASTEXITCODE -ne 0) { throw 'Attivazione del manifest sul server fallita' }

# --- verifica pubblica
$check = Invoke-RestMethod "https://pietrodefilippis.it/updates/tk-desk.json?t=$([DateTime]::Now.Ticks)" -TimeoutSec 15
if ($check.version -ne $version) { throw "Il manifest pubblico non mostra $version" }
foreach ($f in $uploads) {
    $url = "$baseUrl/" + (Split-Path $f -Leaf)
    $resp = Invoke-WebRequest $url -Method Head -UseBasicParsing -TimeoutSec 30
    if ([int64]$resp.Headers['Content-Length'] -ne (Get-Item $f).Length) { throw "Dimensione errata online: $url" }
}
Write-Host "   manifest e file online verificati"

# --- cartella Dropbox: Windows (ZIP portatile), Mac (dmg) e Linux (AppImage), solo l'ultima versione
New-Item -ItemType Directory -Force "$dropbox\Windows", "$dropbox\Mac", "$dropbox\Linux" | Out-Null
Get-ChildItem "$dropbox\Windows" -File | Where-Object { $_.Name -notlike "*$version*" } | Remove-Item -Force
Copy-Item $winPortable "$dropbox\Windows\" -Force
Copy-Item "$dist\tk-desk-setup-$version.exe" "$dropbox\Windows\" -Force
if (-not $SoloWindows) {
    Get-ChildItem "$dropbox\Mac" -File | Where-Object { $_.Name -notlike "*$version*" } | Remove-Item -Force
    foreach ($a in $assets | Where-Object { $_.key -like 'mac-*' }) { Copy-Item $a.file "$dropbox\Mac\" -Force }
    Get-ChildItem "$dropbox\Linux" -File | Where-Object { $_.Name -notlike "*$version*" } | Remove-Item -Force
    foreach ($a in $assets | Where-Object { $_.key -like 'linux-*' }) { Copy-Item $a.file "$dropbox\Linux\" -Force }
}
# il progetto sta già in Dropbox (CLAUDE\dev\tk-desk) e su GitHub: niente copia «progetto»

if ($SoloWindows) { Write-Host "== tk-desk $version pubblicato SOLO per Windows (Mac e Linux in attesa delle build GitHub)." }
else { Write-Host "== tk-desk $version pubblicato per Windows, Mac e Linux." }
