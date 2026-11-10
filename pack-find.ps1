$p = Get-Command aliyunpan.exe -ErrorAction SilentlyContinue
if ($p) { Write-Host ("PATH: " + $p.Source) } else { Write-Host "not in PATH" }
Write-Host "--- searching C:\ D:\ (depth 3) ---"
Get-ChildItem -Path 'C:\','D:\' -Filter 'aliyunpan.exe' -Recurse -Depth 3 -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName }
