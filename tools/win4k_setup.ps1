# Set up a Windows Server test box for Warband on a 4K scaled desktop (WB-021): the operator's SSH access,
# Python with pyglet, and the published portable build.  Run in an elevated PowerShell on the box:
#   iwr https://raw.githubusercontent.com/ikamensh/saga-online/main/tools/win4k_setup.ps1 -OutFile setup.ps1; powershell -ExecutionPolicy Bypass -File .\setup.ps1
# The same script is the instance's first-boot user data; running it again is harmless.
param([string]$WarbandVersion = "0.2.16")
$ErrorActionPreference = 'Continue'
Start-Transcript -Path C:\win4k-setup.log -Append
$key = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIABFC6kHFYDxMKNIXyGEvbJVUiGbczEeGOUJCeQYNnQE raven'
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Set-Service -Name sshd -StartupType Automatic
New-Item -ItemType Directory -Force -Path C:\ProgramData\ssh | Out-Null
Set-Content -Path C:\ProgramData\ssh\administrators_authorized_keys -Value $key -Encoding ascii
icacls C:\ProgramData\ssh\administrators_authorized_keys /inheritance:r /grant 'Administrators:F' /grant 'SYSTEM:F' | Out-Null
New-Item -Path 'HKLM:\SOFTWARE\OpenSSH' -Force | Out-Null
New-ItemProperty -Path 'HKLM:\SOFTWARE\OpenSSH' -Name DefaultShell -Value 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' -PropertyType String -Force | Out-Null
Start-Service sshd
if (-not (Get-NetFirewallRule -DisplayName 'OpenSSH' -ErrorAction SilentlyContinue)) { New-NetFirewallRule -DisplayName 'OpenSSH' -Direction Inbound -Protocol TCP -LocalPort 22 -Action Allow | Out-Null }
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
if (-not (Test-Path 'C:\Program Files\Python313\python.exe')) {
  Invoke-WebRequest 'https://www.python.org/ftp/python/3.13.2/python-3.13.2-amd64.exe' -OutFile C:\python-3.13.2-amd64.exe
  Start-Process C:\python-3.13.2-amd64.exe -ArgumentList '/quiet InstallAllUsers=1 PrependPath=1 Include_test=0' -Wait
}
& 'C:\Program Files\Python313\python.exe' -m pip install --quiet pyglet==2.1.16 pillow==12.3.0
New-Item -ItemType Directory -Force -Path C:\Warband, C:\win4k | Out-Null
if (-not (Test-Path C:\Warband\portable)) {
  Invoke-WebRequest "https://github.com/ikamensh/warband/releases/download/v$WarbandVersion/Warband-$WarbandVersion-windows-x64-portable.zip" -OutFile C:\Warband\portable.zip
  Expand-Archive -Path C:\Warband\portable.zip -DestinationPath C:\Warband\portable -Force
}
Get-ChildItem C:\Warband\portable -Recurse -Filter '*.exe' | Select-Object -First 3 FullName | Out-String | Write-Output
Get-Service sshd | Out-String | Write-Output
Stop-Transcript
