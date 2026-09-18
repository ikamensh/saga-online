# A Windows test box without a person at it

For a report from a Windows desktop that neither this Mac nor a CI runner can
stand in for: display scaling, a first run, an installer on a real account.
GitHub's Windows runners cannot change their session's resolution or scaling
inside a job. A Scaleway Windows instance can be created, set up, given an
interactive desktop of any size and scaling, used and deleted entirely from
this laptop, with no login typed by anyone. First used 2026-09-18 for
Warband's 4K report ([WB-021](../../warband/BACKLOG.md),
[S2D-015](../../saga2d/BACKLOG.md)).

## Create

```bash
ssh-keygen -t rsa -b 4096 -N "" -f ~/.ssh/<box>_rsa          # Scaleway encrypts the admin password to an RSA key
scw iam ssh-key create name=<box> public-key="$(cat ~/.ssh/<box>_rsa.pub)" project-id=<saga2d project>
scw instance security-group create name=<box> inbound-default-policy=drop zone=fr-par-1
scw instance security-group create-rule security-group-id=<sg> protocol=TCP direction=inbound action=accept \
    ip-range=<this laptop's address>/32 dest-port-from=22 zone=fr-par-1       # and again for 3389
scw instance server create type=POP2-2C-8G-WIN image=windows_server_2022 zone=fr-par-1 ip=new name=<box> \
    security-group-id=<sg> admin-password-encryption-ssh-key-id=<iam key id> tags.0=with-ssh --wait
umask 077; scw instance server get-rdp-password <id> zone=fr-par-1 key=~/.ssh/<box>_rsa -o json > ~/secrets/<box>-rdp.json
```

The credentials are the `saga2d-deploy` section of `~/secrets/scaleway.md`
(`tools/deploy_online.py`'s `load_scaleway_key` reads them); creating the IAM
key needs the laptop's admin key. About 0.18 € an hour while it runs; the
password is ready a few minutes after the first boot and is never printed.

- **`with-ssh` must be on the instance when it is created.** Scaleway's Windows
  images ignore user data; their init agent enables the bundled OpenSSH server
  and loads the project's IAM keys only at first boot, and only with that tag.
  Adding it later and rebooting does nothing (the first box was replaced for
  this).
- SSH is then `ssh -i ~/.ssh/<box>_rsa Administrator@<ip>`. The default shell
  is `cmd.exe`: call `powershell -NoProfile -Command ...` or, for anything
  with quotes, copy a `.ps1` over and run it with `-File`. A quoted command
  does not survive ssh, cmd and PowerShell in a row.
- **RDP comes with the legacy security layer and no network-level
  authentication.** That is why a Mac's Windows App shows the remote logon
  screen, where a password cannot be pasted, and why a scripted client cannot
  authenticate. Switch the listener to TLS with NLA and reboot (restarting
  `TermService` hangs in `STOP_PENDING`):

  ```bat
  reg add "HKLM\SYSTEM\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp" /v SecurityLayer /t REG_DWORD /d 2 /f
  reg add "HKLM\SYSTEM\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp" /v UserAuthentication /t REG_DWORD /d 1 /f
  shutdown /r /t 2 /f
  ```
- The instance has no GPU. A game needs Mesa's software driver beside its
  executable: `opengl32.dll` and `libgallium_wgl.dll` from the mesa-dist-win
  archive Warband's CI pins, with `GALLIUM_DRIVER=llvmpipe`. Beside
  `python.exe` too when a script opens a pyglet window.

## A desktop session, and work inside it

```bash
A=(--host <ip> --ssh-key ~/.ssh/<box>_rsa)
python tools/win_desktop.py $A open --secret ~/secrets/<box>-rdp.json --size 3840x2160 --scale 200
python tools/win_desktop.py $A push tools/win_box/*.ps1 tools/win_box/screen_report.py
python tools/win_desktop.py $A run warband_check.ps1 --done session_check.done
python tools/win_desktop.py $A fetch --to docs/evidence/<case> title.png match.png screen_report.json
python tools/win_desktop.py $A close
```

- `open` runs FreeRDP inside a container with a virtual X display (Docker
  through OrbStack: `orb start`). Nothing appears on this Mac; the session
  lives as long as the container. The client decides the desktop's size and
  scaling, and FreeRDP sends both; Windows App on the Mac ignores
  `desktopscalefactor` and, unless the `.rdp` says `dynamic resolution:i:0`,
  resizes the session to its own window. Forcing a scale from the server side
  (`LogPixels`, `IgnoreClientDesktopScaleFactor`) did not work. A scaling
  applies at logon, so `open` logs an earlier session off first.
- A process started over SSH has no desktop. `run` registers a scheduled task
  with an interactive logon for the same user and starts it: the script runs
  inside the RDP session (`tools/win_box/start_in_session.ps1`).
- `tools/win_box/capture.ps1` screenshots the session's desktop. It declares
  itself DPI aware first; an unaware process sees a 200 % desktop as half its
  size and grabs a corner. A disconnected session cannot be captured, so the
  container stays up while scripts run.
- `tools/win_box/screen_report.py` records what Windows says before and after
  DPI awareness, every pyglet screen, a fixed-size probe window and an engine
  probe (`Game(resolution=None)`); `warband_check.ps1` adds Warband's title,
  New game screen and first match, from the published build or, with
  `source` in `C:\win4k\check.args`, from `C:\src` on the engine installed in
  the box's Python. llvmpipe draws 3840×2160 slowly: the waits are generous.
- To watch a session yourself, connect Windows App with a file that says
  `dynamic resolution:i:0`, `use multimon:i:0` and the size; with NLA on, the
  password prompt is the Mac's own and takes a paste. Your connection takes
  the session over from the container.

## Delete

The instance with its volume, the flexible IP, the security group and the IAM
key (`scw instance server terminate <id> with-ip=true with-block=true`, then
the group and `scw iam ssh-key delete`), and the two files under `~/secrets`
and `~/.ssh`. Nothing on the box is worth keeping; evidence is copied off it
as it is produced.
