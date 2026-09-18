# Inside the interactive session (started by start_in_session.ps1): what Windows, pyglet and the engine see, then the
# game's title, New game screen and first match, each captured from the desktop.  Results land in C:\win4k.
# C:\win4k\check.args (optional, one line) selects the game: "source" runs python -m warband from C:\src with the
# engine installed in the box's Python instead of the published build; "tag=NAME" prefixes the frames.
$ErrorActionPreference = 'Continue'
Start-Transcript -Path C:\win4k\session_check.log | Out-Null
Add-Type -AssemblyName System.Windows.Forms
$env:GALLIUM_DRIVER = 'llvmpipe'; $env:LP_NUM_THREADS = '2'
$options = if (Test-Path C:\win4k\check.args) { (Get-Content C:\win4k\check.args -Raw).Trim() } else { '' }
$tag = if ($options -match 'tag=(\S+)') { $Matches[1] + '-' } else { '' }
"options: $options"
"AppliedDPI: $((Get-ItemProperty 'HKCU:\Control Panel\Desktop\WindowMetrics' -ErrorAction SilentlyContinue).AppliedDPI)"
& 'C:\Program Files\Python313\python.exe' C:\win4k\screen_report.py 2>&1 | Out-String
powershell -NoProfile -ExecutionPolicy Bypass -File C:\win4k\capture.ps1 -Name "${tag}desktop-before"
if ($options -match 'source') {
  $env:PYTHONPATH = 'C:\src'
  $game = Start-Process -FilePath 'C:\Program Files\Python313\python.exe' -ArgumentList '-m', 'warband' -WorkingDirectory 'C:\src' -PassThru
} else {
  $game = Start-Process -FilePath 'C:\Warband\portable\Warband\Warband.exe' -WorkingDirectory 'C:\Warband\portable\Warband' -PassThru
}
Start-Sleep -Seconds 75
powershell -NoProfile -ExecutionPolicy Bypass -File C:\win4k\capture.ps1 -Name "${tag}title"
$shell = New-Object -ComObject WScript.Shell
$null = $shell.AppActivate($game.Id)
Start-Sleep -Seconds 1
[System.Windows.Forms.SendKeys]::SendWait('n')
Start-Sleep -Seconds 8
powershell -NoProfile -ExecutionPolicy Bypass -File C:\win4k\capture.ps1 -Name "${tag}newgame"
[System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
Start-Sleep -Seconds 90
powershell -NoProfile -ExecutionPolicy Bypass -File C:\win4k\capture.ps1 -Name "${tag}match"
"game running: $(-not $game.HasExited); exit code: $($game.ExitCode)"
if (-not $game.HasExited) { Stop-Process -Id $game.Id -Force }
Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.Path -like '*Python313*' } | Stop-Process -Force -ErrorAction SilentlyContinue
"done" | Set-Content C:\win4k\session_check.done
Stop-Transcript | Out-Null
