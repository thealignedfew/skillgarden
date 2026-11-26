# sampler.ps1  ramgovern: a small, read-only machine sampler (0.2.0).
#
# Writes one JSON line every -IntervalSec seconds to samples-YYYYMMDD.jsonl in the ramgovern home. The brake suggester and
# the dashboard read these lines. It only reads: free memory, commit charge, total processor use, the application in front,
# seconds since the last keyboard or mouse input, and the five busiest processes. It changes nothing, stops nothing and
# sends nothing anywhere.
#
# Line format (one per sample, ASCII):
#   {"t":"2026-01-15T09:30:00","availMB":3210,"commitPct":71.4,"cpuPct":38.2,"fg":"chrome","idleSec":4,
#    "top5":["name 171.6","name 96.7", ...]}
# top5 is "process name, percent of ONE core", summed over copies of that name, busiest first. A field the machine cannot
# supply is left out of the line, not written as zero.
#
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\sampler.ps1              runs until stopped (Ctrl+C)
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\sampler.ps1 -Once       one line after a 2 second look, then exit
#   -OutDir <folder>        where samples-*.jsonl go (default: the ramgovern home, see below)
#   -IntervalSec <n>        seconds between samples, 5 to 600 (default 15)
#
# The ramgovern home is the folder named by the environment variable RAMGOVERN_HOME, or else the folder holding govern.json
# (this script's folder or the one above it), or else .threadops\ramgovern under the user profile. Settings and data live there, never inside the skill folder. Files older than 14 days are left for you to clear.
# Windows PowerShell 5.1 safe.
param(
    [string]$OutDir = '',
    [int]$IntervalSec = 15,
    [switch]$Once
)
$ErrorActionPreference = 'Continue'
if ($IntervalSec -lt 5) { $IntervalSec = 5 }
if ($IntervalSec -gt 600) { $IntervalSec = 600 }
if (-not $OutDir) {
    $h = $env:RAMGOVERN_HOME
    if (-not $h) {
        foreach ($d in @($PSScriptRoot, (Split-Path $PSScriptRoot -Parent))) { if ($d -and (Test-Path (Join-Path $d 'govern.json'))) { $h = $d; break } }
    }
    if (-not $h) { $h = Join-Path $env:USERPROFILE '.threadops\ramgovern' }
    $OutDir = $h
}
if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir -Force | Out-Null }

Add-Type -TypeDefinition @'
using System; using System.Runtime.InteropServices; using System.Text;
public static class RgSample {
  [StructLayout(LayoutKind.Sequential)] public struct LII { public uint cbSize; public uint dwTime; }
  [DllImport("user32.dll")] static extern bool GetLastInputInfo(ref LII p);
  [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  public static long IdleSec() { LII l = new LII(); l.cbSize = 8; if (!GetLastInputInfo(ref l)) return -1; return ((uint)Environment.TickCount - l.dwTime) / 1000; }
  public static int ForegroundPid() { uint pid; IntPtr h = GetForegroundWindow(); if (h == IntPtr.Zero) return 0; GetWindowThreadProcessId(h, out pid); return (int)pid; }
}
'@

function Get-Snapshot {
    # name -> total processor seconds over every copy, plus the pid list, so a later snapshot gives percent of one core
    $m = @{}
    foreach ($p in @(Get-Process -ErrorAction SilentlyContinue)) {
        try {
            $n = $p.ProcessName.ToLower()
            $cpu = 0.0
            if ($p.TotalProcessorTime) { $cpu = $p.TotalProcessorTime.TotalSeconds }
            if ($m.ContainsKey($n)) { $m[$n] += $cpu } else { $m[$n] = $cpu }
        } catch { }
    }
    return $m
}

function Write-Sample($before, $beforeAt) {
    $now = Get-Date
    $after = Get-Snapshot
    $script:nextSnap = $after; $script:nextAt = $now
    $secs = ($now - $beforeAt).TotalSeconds
    if ($secs -lt 0.5) { $secs = 0.5 }
    $rec = [ordered]@{ t = $now.ToString('yyyy-MM-ddTHH:mm:ss') }
    try {
        $os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
        $rec.availMB = [int]($os.FreePhysicalMemory / 1KB)
        $lim = [double]$os.TotalVirtualMemorySize; $free = [double]$os.FreeVirtualMemory
        if ($lim -gt 0) { $rec.commitPct = [math]::Round(100 * ($lim - $free) / $lim, 1) }
    } catch { }
    try {
        $cpu = (Get-CimInstance Win32_Processor -ErrorAction Stop | Measure-Object LoadPercentage -Average).Average
        if ($null -ne $cpu) { $rec.cpuPct = [math]::Round([double]$cpu, 1) }
    } catch { }
    try {
        $fp = [RgSample]::ForegroundPid()
        if ($fp -gt 0) { $rec.fg = (Get-Process -Id $fp -ErrorAction Stop).ProcessName.ToLower() }
    } catch { }
    $idle = [RgSample]::IdleSec()
    if ($idle -ge 0) { $rec.idleSec = [int]$idle }
    $rows = @()
    foreach ($k in $after.Keys) {
        if ($k -eq 'idle' -or $k -eq 'system idle process') { continue }
        $prev = 0.0
        if ($before.ContainsKey($k)) { $prev = $before[$k] }
        $d = $after[$k] - $prev
        if ($d -gt 0) { $rows += [pscustomobject]@{ n = $k; c = [math]::Round(100 * $d / $secs, 1) } }
    }
    $rec.top5 = @($rows | Sort-Object c -Descending | Select-Object -First 5 | ForEach-Object { "$($_.n) $($_.c)" })
    $line = $rec | ConvertTo-Json -Compress -Depth 3
    $file = Join-Path $OutDir ('samples-' + $now.ToString('yyyyMMdd') + '.jsonl')
    Add-Content -Path $file -Value $line -Encoding UTF8
    return $line
}

$snap = Get-Snapshot; $at = Get-Date
if ($Once) {
    Start-Sleep -Seconds 2
    Write-Output (Write-Sample $snap $at)
    exit 0
}
while ($true) {
    Start-Sleep -Seconds $IntervalSec
    try { [void](Write-Sample $snap $at) } catch { }
    $snap = $script:nextSnap; $at = $script:nextAt
}
