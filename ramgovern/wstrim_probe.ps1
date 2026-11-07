# wstrim_probe.ps1  ramgovern, stage 0 probe: see what a trim would release before installing anything.
# Dry run by default: lists the idle processes (zero CPU over -IdleSeconds, not the foreground window, not the claude.exe
# this probe runs under) and the resident memory a trim would release.
# -Apply trims them with psapi EmptyWorkingSet: pages go to the standby list, then the compressed store, then the pagefile;
# the process keeps running and faults pages back on demand. Nothing to undo.
# A one-off trim does not last: idle sessions regrow within the hour as they wake for their own work. That is why the
# Governor (govern.ps1) runs on a cadence and, optionally, right after each unattended session's own turn.
param(
    [switch]$Apply,
    [int]$IdleSeconds = 10,
    [string[]]$Names = @('claude'),
    [string]$Log = ''
)
if (-not $Log) { $Log = Join-Path $PSScriptRoot 'wstrim_probe.log' }
$code = @"
using System;
using System.Runtime.InteropServices;
public static class WsTrim {
  [DllImport("psapi.dll", SetLastError=true)] static extern bool EmptyWorkingSet(IntPtr h);
  [DllImport("kernel32.dll", SetLastError=true)] static extern IntPtr OpenProcess(uint access, bool inherit, int pid);
  [DllImport("kernel32.dll", SetLastError=true)] static extern bool CloseHandle(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  public static int Trim(int pid) {
    IntPtr h = OpenProcess(0x0100 | 0x0400, false, pid);   // PROCESS_SET_QUOTA | PROCESS_QUERY_INFORMATION
    if (h == IntPtr.Zero) return -Marshal.GetLastWin32Error();
    bool ok = EmptyWorkingSet(h);
    int err = ok ? 0 : Marshal.GetLastWin32Error();
    CloseHandle(h);
    return err;
  }
}
"@
Add-Type -TypeDefinition $code

[uint32]$fg = 0
[void][WsTrim]::GetWindowThreadProcessId([WsTrim]::GetForegroundWindow(), [ref]$fg)

# the claude.exe this probe runs under (when run from a Claude Code session), found by walking up from this PowerShell
$cur = Get-CimInstance Win32_Process -Filter "ProcessId=$PID"; $own = 0
for ($i = 0; $i -lt 8 -and $cur; $i++) {
    if ($cur.Name -eq 'claude.exe') { $own = $cur.ProcessId; break }
    $cur = Get-CimInstance Win32_Process -Filter "ProcessId=$($cur.ParentProcessId)"
}

$procs = Get-Process -Name $Names -ErrorAction SilentlyContinue
$before = @{}; $procs | ForEach-Object { $before[$_.Id] = $_.CPU }
Start-Sleep $IdleSeconds
$idle = Get-Process -Name $Names -ErrorAction SilentlyContinue | Where-Object {
    $_.Id -ne $own -and [uint32]$_.Id -ne $fg -and $before.ContainsKey($_.Id) -and
    ([double]$_.CPU - [double]$before[$_.Id]) -lt 0.05
}

$free0 = [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1KB)
$ws0 = [math]::Round(($idle | Measure-Object WorkingSet64 -Sum).Sum / 1MB)
$stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'

if (-not $Apply) {
    "$stamp DRY RUN: $($idle.Count) idle of $($procs.Count) ($($Names -join ',')); resident $ws0 MB would be trimmed; free RAM $free0 MB"
    return
}

$ok = 0; $fail = 0; $t0 = Get-Date
foreach ($p in $idle) { if ([WsTrim]::Trim($p.Id) -eq 0) { $ok++ } else { $fail++ } }
$ms = [math]::Round(((Get-Date) - $t0).TotalMilliseconds)
Start-Sleep 2
$idle | ForEach-Object { $_.Refresh() }
$ws1 = [math]::Round(($idle | Measure-Object WorkingSet64 -Sum).Sum / 1MB)
$free1 = [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1KB)
$line = "$stamp APPLY: trimmed $ok ($fail failed) of $($procs.Count) $($Names -join ',') in $ms ms; resident $ws0 -> $ws1 MB; free RAM $free0 -> $free1 MB"
$line
Add-Content -Path $Log -Value $line
