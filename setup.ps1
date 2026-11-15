<#
  Laptop Remote -- one-shot setup for a fresh Windows laptop.
  Downloads the project, installs what it needs, and starts it so the phone can
  reach this laptop from anywhere. Run it through setup.bat (which asks for the
  administrator rights this needs). uninstall.bat undoes every step below.

  Every value you might change lives here at the top; nothing is hidden further down.
#>
$ErrorActionPreference = "Stop"

$Repo        = "https://github.com/zuhaibx69/laptop-remote"   # the public project
$Branch      = "main"
$Install     = Join-Path $env:USERPROFILE "laptop-remote"     # where it is set up
$Cloudflared = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
$PyWinget    = "Python.Python.3.12"                           # used only if Python is missing

function Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Find-Python {
    foreach ($name in "python", "py") {
        $found = Get-Command $name -ErrorAction SilentlyContinue
        if ($found -and (& $found.Source --version 2>$null)) { return $found.Source }
    }
    $guess = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
    if (Test-Path $guess) { return $guess }
    return $null
}

# 1. The folder, and a Windows Defender exclusion for JUST this folder, added
#    BEFORE the files arrive so the server file is never deleted. Defender stays
#    on for the whole rest of the laptop. On a laptop with other antivirus this
#    line simply does nothing (caught and ignored).
Step "Preparing $Install and excluding only this folder from Windows Defender"
New-Item -ItemType Directory -Force -Path $Install | Out-Null
try { Add-MpPreference -ExclusionPath $Install -ErrorAction Stop; Write-Host "   Defender exclusion added." }
catch { Write-Host "   (Could not set a Defender exclusion -- another antivirus may manage this laptop.)" -ForegroundColor Yellow }

# 2. Download the project as a zip (no git needed) and unpack it into $Install.
Step "Downloading the project from $Repo"
$zip = Join-Path $env:TEMP "laptop-remote.zip"
Invoke-WebRequest "$Repo/archive/refs/heads/$Branch.zip" -OutFile $zip -UseBasicParsing
$unzip = Join-Path $env:TEMP "laptop-remote-unzip"
if (Test-Path $unzip) { Remove-Item $unzip -Recurse -Force }
Expand-Archive $zip -DestinationPath $unzip -Force
Copy-Item (Join-Path $unzip "laptop-remote-$Branch\*") $Install -Recurse -Force
Remove-Item $zip, $unzip -Recurse -Force
Set-Location $Install

# 3. Python: use the one already here, or install it once.
Step "Checking Python"
$py = Find-Python
if (-not $py) {
    Write-Host "   Python not found; installing it with winget..."
    winget install -e --id $PyWinget --accept-source-agreements --accept-package-agreements --silent
    $py = Find-Python
}
if (-not $py) { throw "Python could not be installed. Install Python 3.12 from python.org, then run setup again." }
Write-Host "   Using $py"

# 4. A private virtual environment and the four packages the server needs.
Step "Installing the server's packages (aiohttp, pillow, psutil, pyyaml)"
& $py -m venv .venv
$venvPy = Join-Path $Install ".venv\Scripts\python.exe"
& $venvPy -m pip install --upgrade pip --quiet
& $venvPy -m pip install -r requirements.txt --quiet

# 5. cloudflared: the tunnel that gives this laptop a public address without a
#    fixed IP. Too big for the repo, so it is downloaded here.
Step "Downloading the tunnel (cloudflared)"
New-Item -ItemType Directory -Force -Path (Join-Path $Install "tools") | Out-Null
Invoke-WebRequest $Cloudflared -OutFile (Join-Path $Install "tools\cloudflared.exe") -UseBasicParsing

# 6. Start with Windows, and start now.
Step "Setting it to start with Windows"
& $venvPy -m remote --install
Step "Starting the server"
$pyw = Join-Path $Install ".venv\Scripts\pythonw.exe"
Start-Process -FilePath $pyw -ArgumentList "-m", "remote" -WorkingDirectory $Install

# 7. Show how to connect from the phone.
Step "Where to connect from the phone"
$secretFile = Join-Path $Install "data\secret.json"
for ($i = 0; $i -lt 30 -and -not (Test-Path $secretFile); $i++) { Start-Sleep 1 }
if (Test-Path $secretFile) {
    $secret = Get-Content $secretFile -Raw | ConvertFrom-Json
    Write-Host "`n   1. On the iPhone, install the free app 'ntfy' from the App Store." -ForegroundColor Green
    Write-Host "   2. In ntfy, subscribe to this topic:  $($secret.topic)" -ForegroundColor Green
    Write-Host "      Whenever the laptop comes online, ntfy sends the link; tap it to open the app," -ForegroundColor Green
    Write-Host "      then use Share -> Add to Home Screen so it opens like an app." -ForegroundColor Green
    $addr = Join-Path $Install "data\address.txt"
    for ($i = 0; $i -lt 20 -and -not (Test-Path $addr); $i++) { Start-Sleep 1 }
    if (Test-Path $addr) { Write-Host "`n   Public address right now: $(Get-Content $addr)/#key=$($secret.key)" -ForegroundColor Green }
    Write-Host "`n   On this laptop you can also open:  http://127.0.0.1:8095/#key=$($secret.key)" -ForegroundColor Green
} else {
    Write-Host "   The server did not write its key yet; check $Install\logs\remote.log" -ForegroundColor Yellow
}
Write-Host "`nDone. The laptop is now a remote-controlled server." -ForegroundColor Cyan
