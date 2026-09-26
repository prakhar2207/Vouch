$sh = New-Object -ComObject WScript.Shell

$shortcuts = @(
    "C:\Users\prakh\OneDrive\Desktop\Vouch Accounting & ERP.lnk",
    "C:\Users\prakh\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Chrome Apps\Vouch Accounting & ERP.lnk",
    "C:\Users\prakh\AppData\Local\Google\Chrome\User Data\Default\Web Applications\_crx_mmmjojggeicfkcanbnmmegpjedkfdjnk\Vouch Accounting & ERP.lnk"
)

$icoPath = "C:\Users\prakh\AppData\Local\Google\Chrome\User Data\Default\Web Applications\_crx_mmmjojggeicfkcanbnmmegpjedkfdjnk\Vouch Accounting & ERP.ico"

foreach ($lnk in $shortcuts) {
    if (Test-Path $lnk) {
        $sc = $sh.CreateShortcut($lnk)
        $sc.IconLocation = "$icoPath,0"
        $sc.Save()
        (Get-Item $lnk).LastWriteTime = Get-Date
        Write-Output "Updated shortcut: $lnk"
    }
}

# Invalidate Windows Explorer icon cache so desktop reflects immediately
$code = @'
using System;
using System.Runtime.InteropServices;
public class ShellNotification {
    [DllImport("Shell32.dll")]
    public static extern void SHChangeNotify(int wEventId, int uFlags, IntPtr dwItem1, IntPtr dwItem2);
}
'@
Add-Type -TypeDefinition $code -Language CSharp
[ShellNotification]::SHChangeNotify(0x08000000, 0, [IntPtr]::Zero, [IntPtr]::Zero)
Write-Output "Windows Shell icon cache refresh signaled successfully!"
