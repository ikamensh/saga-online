# Screenshot of the whole virtual screen of the interactive session into C:\win4k\<name>.png.
# The process declares itself DPI aware first: an unaware one sees a scaled desktop as 1920x1080 and grabs a corner.
param([string]$Name = "desktop")
Add-Type -TypeDefinition 'using System.Runtime.InteropServices; public class Dpi { [DllImport("user32.dll")] public static extern bool SetProcessDPIAware(); }'
[Dpi]::SetProcessDPIAware() | Out-Null
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
New-Item -ItemType Directory -Force -Path C:\win4k | Out-Null
$bounds = [System.Windows.Forms.SystemInformation]::VirtualScreen
$bitmap = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
$bitmap.Save("C:\win4k\$Name.png", [System.Drawing.Imaging.ImageFormat]::Png)
"$($bounds.Width)x$($bounds.Height) -> C:\win4k\$Name.png"
