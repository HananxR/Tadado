// Temporary helper: list top-level windows of a PID (including hidden ones).
Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class EnumW {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
}
"@
$target = [uint32]$args[0]
$list = New-Object System.Collections.ArrayList
$cb = [EnumW+EnumProc]{
  param($h, $l)
  $pid2 = [uint32]0
  [void][EnumW]::GetWindowThreadProcessId($h, [ref]$pid2)
  if ($pid2 -eq $target) {
    $sb = New-Object System.Text.StringBuilder 512
    [void][EnumW]::GetWindowText($h, $sb, 512)
    [void]$list.Add(("hwnd=0x{0:X} visible={1} iconic={2} title=[{3}]" -f $h.ToInt64(), [EnumW]::IsWindowVisible($h), [EnumW]::IsIconic($h), $sb.ToString()))
  }
  return $true
}
[void][EnumW]::EnumWindows($cb, [IntPtr]::Zero)
$list | ForEach-Object { Write-Output $_ }
Write-Output ("foreground=0x{0:X}" -f ([EnumW]::GetForegroundWindow()).ToInt64())
