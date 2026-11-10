# Temporary real-window check for the tray hotkey wake-up fix.
# Scenario: minimize the window -> press Ctrl+Shift+Space -> it must be restored,
# visible and focused. e2e cannot cover this; only a real window can.
# NOTE: ASCII only on purpose (Windows PowerShell reads .ps1 as ANSI without BOM).

Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class W32 {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
}
"@

# start our own debug build and scope the window lookup to that PID, so a
# pre-existing instance cannot steal the global hotkey from us.
$exe = "d:\MyCCProject\Test\desktop\src-tauri\target\debug\desktop.exe"
$app = Start-Process -FilePath $exe -PassThru
Start-Sleep -Seconds 8

$script:found = [IntPtr]::Zero
$cb = [W32+EnumProc]{
  param($h, $l)
  $owner = [uint32]0
  [void][W32]::GetWindowThreadProcessId($h, [ref]$owner)
  if ($owner -eq $app.Id) {
    $sb = New-Object System.Text.StringBuilder 256
    [void][W32]::GetWindowText($h, $sb, 256)
    if ($sb.ToString() -eq "Tadado2") { $script:found = $h; return $false }
  }
  return $true
}
[void][W32]::EnumWindows($cb, [IntPtr]::Zero)
$hwnd = $script:found

if ($hwnd -eq [IntPtr]::Zero) {
  Stop-Process -Id $app.Id -Force -ErrorAction SilentlyContinue
  Write-Output "FAIL no Tadado2 window for pid $($app.Id)"
  exit 1
}
Write-Output ("pid $($app.Id)  hwnd 0x{0:X}" -f $hwnd.ToInt64())

$script:fail = 0
function State($tag) {
  $iconic = [W32]::IsIconic($hwnd)
  $vis = [W32]::IsWindowVisible($hwnd)
  $fg = ([W32]::GetForegroundWindow() -eq $hwnd)
  Write-Host ("{0,-22} minimized={1,-5} visible={2,-5} foreground={3}" -f $tag, $iconic, $vis, $fg)
  return @($iconic, $vis, $fg)
}

function Check($name, $ok) {
  if ($ok) { Write-Host "OK   $name" } else { Write-Host "FAIL $name"; $script:fail++ }
}

$ws = New-Object -ComObject WScript.Shell

[void](State "startup")

# --- case 1: minimized, then hotkey -> must restore + focus
[void][W32]::ShowWindow($hwnd, 6)   # SW_MINIMIZE
Start-Sleep -Milliseconds 700
[void](State "after-minimize")
$ws.SendKeys("^+ ")
Start-Sleep -Milliseconds 900
$s = State "after-hotkey"
Check "minimized + hotkey restores window" (-not $s[0])
Check "minimized + hotkey shows window" ($s[1])
Check "minimized + hotkey gives focus" ($s[2])

# --- case 2: visible, then hotkey -> must hide to tray
$ws.SendKeys("^+ ")
Start-Sleep -Milliseconds 900
$s = State "after-second-hotkey"
Check "visible + hotkey hides window" (-not $s[1])

# --- case 3: hidden, then hotkey -> must show + focus
$ws.SendKeys("^+ ")
Start-Sleep -Milliseconds 900
$s = State "after-third-hotkey"
Check "hidden + hotkey shows window" ($s[1])
Check "hidden + hotkey gives focus" ($s[2])

Stop-Process -Id $app.Id -Force -ErrorAction SilentlyContinue
Write-Host ("failed checks: " + $script:fail)
exit $script:fail
