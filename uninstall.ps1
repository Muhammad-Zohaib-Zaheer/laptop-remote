<#
  Laptop Remote -- full removal. Undoes, in reverse, every step setup.ps1 did:
  stops the server and the tunnel, removes the start-with-Windows shortcut, removes
  the Windows Defender exclusion, and deletes the installed folder. Run it through
  uninstall.bat (which asks for administrator rights).
#>
$ErrorActionPreference = "Continue"       # keep going even if one part is already gone

$Install = Join-Path $env:USERPROFILE "laptop-remote"
function Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }

# 1. Stop the running server and its tunnel (only the ones from this folder).
Step "Stopping the server and the tunnel"
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" |
    Where-Object { $_.CommandLine -match "remote" -and $_.CommandLine -match [regex]::Escape($Install) } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" |
    Where-Object { $_.CommandLine -match [regex]::Escape($Install) } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

# 2. Remove the start-with-Windows shortcut.
Step "Removing the start-with-Windows shortcut"
$venvPy = Join-Path $Install ".venv\Scripts\python.exe"
if (Test-Path $venvPy) { & $venvPy -m remote --uninstall }
else { Remove-Item (Join-Path ([Environment]::GetFolderPath('Startup')) "Laptop Remote.lnk") -ErrorAction SilentlyContinue }

# 3. Remove the Windows Defender exclusion for the folder.
Step "Removing the Windows Defender exclusion"
try { Remove-MpPreference -ExclusionPath $Install -ErrorAction Stop; Write-Host "   Exclusion removed." }
catch { Write-Host "   (No Defender exclusion to remove.)" -ForegroundColor Yellow }

# 4. Delete the folder. Because these files live inside it, a short detached
#    command deletes it a few seconds after this window closes.
Step "Deleting $Install"
Start-Process cmd -ArgumentList "/c", "timeout /t 3 >nul & rmdir /s /q `"$Install`"" -WindowStyle Hidden
Write-Host "`nEverything has been undone. The laptop is back to how it was." -ForegroundColor Cyan
