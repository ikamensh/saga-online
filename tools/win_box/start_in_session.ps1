# From an SSH shell: run one of the C:\win4k scripts inside the Administrator's interactive (RDP) session.
param([Parameter(Mandatory)][string]$Script)
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File C:\win4k\$Script"
$principal = New-ScheduledTaskPrincipal -UserId "Administrator" -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Unregister-ScheduledTask -TaskName warband-4k -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName warband-4k -Action $action -Principal $principal -Settings $settings | Out-Null
Start-ScheduledTask -TaskName warband-4k
"started $Script in the interactive session"
