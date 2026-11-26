# brake.ps1  ramgovern brake (0.2.0).
#
# What it does. While you are at the machine (keyboard or mouse within active_window_sec), every process listed as an enabled
# target in brake.json is slowed, never stopped: affinity to the last <threads> logical processors, BelowNormal priority,
# memory priority very low, I/O priority very low. When you have been away active_window_sec, each target is put back as it
# was found. Helpers (child processes named in the target, whose parent is a braked process) get the same.
#
# Safety. Never kill, suspend or trim. Names in $protected are refused even if brake.json lists them. A target's "match" (a
# regex over the command line) narrows it, for example "/automation" for a spreadsheet started by another program, so a copy
# you opened yourself is never touched. brake.json is re-read when it changes; a target appears only with your yes. Every
# brake and release is one line in govern.log ("brake"). Undo: set the target's enabled to false in brake.json, or
# unregister the scheduled task that runs this script. It ships with no targets.
#
# Stress trigger. A target with "trigger": "stress" is braked while the machine is already struggling (free RAM under
# stress.free_mb_below, or commit charge over stress.commit_pct_above) and for stress.hold_sec after the last struggling
# check, whether or not anyone is at the machine. Targets without a trigger follow your presence. On release each process
# gets back the affinity and priority it had before the brake, not a default.
#
# Memory and drive sampler. Once a minute it writes one line to procmem-YYYYMMDD.jsonl beside govern.log: the twelve process
# names holding the most RAM (working set, summed over copies, with private bytes and copy count), commit charge and limit,
# page file use, and per physical disk the read and write MB/s, percent idle and queue, and per volume the free space.
# Read-only. Files older than 14 days are left for you to clear.
#
# Where files live: -Config and -Log default to brake.json and govern.log in the ramgovern home, which is the folder named by
# the environment variable RAMGOVERN_HOME, or else the folder holding govern.json (this script's folder or the one above
# it), or else .threadops\ramgovern under your user profile.
param([string]$Config = '', [string]$Log = '')
function Get-RgHome {
  if ($env:RAMGOVERN_HOME) { return $env:RAMGOVERN_HOME }
  foreach ($d in @($PSScriptRoot, (Split-Path $PSScriptRoot -Parent))) { if ($d -and (Test-Path (Join-Path $d 'govern.json'))) { return $d } }
  return (Join-Path $env:USERPROFILE '.threadops\ramgovern')
}
$rgHome = Get-RgHome
if (-not (Test-Path $rgHome)) { New-Item -ItemType Directory -Path $rgHome -Force | Out-Null }
if (-not $Config) { $Config = Join-Path $rgHome 'brake.json' }
if (-not $Log) { $Log = Join-Path $rgHome 'govern.log' }
$ErrorActionPreference = 'Continue'
$created = $false
$mutex = New-Object System.Threading.Mutex($true, 'Local\RamGovernBrake', [ref]$created)
if (-not $created) { exit 0 }
[void]$mutex
try { (Get-Process -Id $PID).PriorityClass = 'BelowNormal' } catch {}
$protected = @('claude', 'code', 'explorer', 'dwm', 'csrss', 'winlogon', 'lsass', 'services', 'svchost', 'system', 'smss', 'wininit',
  'msmpeng', 'audiodg', 'powershell', 'pwsh', 'conhost', 'windowsterminal', 'zoom', 'chrome', 'msedge')
Add-Type -TypeDefinition @'
using System; using System.Runtime.InteropServices;
public static class RGB {
  [StructLayout(LayoutKind.Sequential)] public struct LII { public uint cbSize; public uint dwTime; }
  [DllImport("user32.dll")] static extern bool GetLastInputInfo(ref LII p);
  public static uint IdleSec() { LII l = new LII(); l.cbSize = 8; if (!GetLastInputInfo(ref l)) return 0; return ((uint)Environment.TickCount - l.dwTime) / 1000; }
  [DllImport("kernel32.dll", SetLastError=true)] static extern IntPtr OpenProcess(uint a, bool i, int pid);
  [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
  [DllImport("kernel32.dll", SetLastError=true)] static extern bool SetProcessInformation(IntPtr h, int c, ref uint v, uint s);
  [DllImport("ntdll.dll")] static extern int NtSetInformationProcess(IntPtr h, int c, ref uint v, int s);
  public static string SetPrio(int pid, uint mem, uint io) {
    IntPtr h = OpenProcess(0x0200, false, pid);
    if (h == IntPtr.Zero) return "open-failed";
    try {
      bool m = SetProcessInformation(h, 0, ref mem, 4);
      int s = NtSetInformationProcess(h, 33, ref io, 4);
      return (m ? "mem-ok" : "mem-fail") + " " + (s == 0 ? "io-ok" : "io-0x" + s.ToString("x"));
    } finally { CloseHandle(h); }
  }
}
'@
$n = [Environment]::ProcessorCount
$allMask = if ($n -ge 64) { [int64]-1 } else { ([int64]1 -shl $n) - 1 }
function Stamp { (Get-Date).ToString('yyyy-MM-dd HH:mm:ss zzz') }
function Say($m) { try { Add-Content -Path $Log -Value ("$(Stamp) brake $m") -Encoding UTF8 } catch {} }
$orig = @{}   # pid -> @(affinity, priority) as found before the first brake
function Apply($p, $brake, $mask) {
  try {
    if ($brake) { if (-not $orig.ContainsKey($p.Id)) { $orig[$p.Id] = @([int64]$p.ProcessorAffinity, [string]$p.PriorityClass) }
      $p.ProcessorAffinity = [IntPtr]$mask; $p.PriorityClass = 'BelowNormal'; $r = [RGB]::SetPrio($p.Id, 1, 0) }
    else { $o = if ($orig.ContainsKey($p.Id)) { $orig[$p.Id] } else { @($allMask, 'Normal') }
      $p.ProcessorAffinity = [IntPtr]$o[0]; $p.PriorityClass = $o[1]; $r = [RGB]::SetPrio($p.Id, 5, 2); $orig.Remove($p.Id) }
    return "$($p.Name) $($p.Id) $r"
  } catch { return "$($p.Name) $($p.Id) failed: $($_.Exception.Message)" }
}
$cfg = $null; $cfgTime = [datetime]::MinValue
$memDir = Split-Path $Log -Parent; $lastMem = [datetime]::MinValue
function SampleMem {
  try {
    $g = Get-Process | Group-Object Name | ForEach-Object {
      $ws = ($_.Group | Measure-Object WorkingSet64 -Sum).Sum; $pv = ($_.Group | Measure-Object PrivateMemorySize64 -Sum).Sum
      [pscustomobject]@{ n = $_.Name; ws = [int]($ws / 1MB); pv = [int]($pv / 1MB); c = $_.Count } } | Sort-Object ws -Descending
    $os = Get-CimInstance Win32_OperatingSystem
    $pf = @(Get-CimInstance Win32_PageFileUsage)
    $rec = [ordered]@{ t = (Get-Date).ToString('s'); availMB = [int]($os.FreePhysicalMemory / 1KB); totalMB = [int]($os.TotalVisibleMemorySize / 1KB)
      commitMB = [int](($os.TotalVirtualMemorySize - $os.FreeVirtualMemory) / 1KB); limitMB = [int]($os.TotalVirtualMemorySize / 1KB)
      pfUsedMB = [int](($pf | Measure-Object CurrentUsage -Sum).Sum); pfPeakMB = [int](($pf | Measure-Object PeakUsage -Sum).Sum); pfSizeMB = [int](($pf | Measure-Object AllocatedBaseSize -Sum).Sum)
      wsAllMB = [int](($g | Measure-Object ws -Sum).Sum); top = @($g | Select-Object -First 12) }
    # Drives: per physical disk, read and write MB/s over 2 s, % idle and queue; per volume, free GB and %. Read-only counters.
    try {
      $cs = (Get-Counter '\PhysicalDisk(*)\Disk Read Bytes/sec','\PhysicalDisk(*)\Disk Write Bytes/sec','\PhysicalDisk(*)\% Idle Time','\PhysicalDisk(*)\Avg. Disk Queue Length' -SampleInterval 2 -MaxSamples 1 -ErrorAction Stop).CounterSamples
      $rec.disk = @($cs | Where-Object InstanceName -ne '_total' | Group-Object InstanceName | ForEach-Object { $x = $_.Group
        [ordered]@{ d = $_.Name; r = [math]::Round((($x | Where-Object Path -match 'read bytes').CookedValue) / 1MB, 1); w = [math]::Round((($x | Where-Object Path -match 'write bytes').CookedValue) / 1MB, 1)
          idle = [int](($x | Where-Object Path -match 'idle').CookedValue); q = [math]::Round((($x | Where-Object Path -match 'queue').CookedValue), 2) } })
      $rec.vol = @(Get-Volume | Where-Object { $_.DriveLetter -and $_.Size -gt 0 } | ForEach-Object { [ordered]@{ v = [string]$_.DriveLetter; freeGB = [int]($_.SizeRemaining / 1GB); freePct = [math]::Round(100.0 * $_.SizeRemaining / $_.Size, 1) } })
    } catch { $rec.diskErr = $_.Exception.Message }
    Add-Content -Path (Join-Path $memDir ('procmem-' + (Get-Date).ToString('yyyyMMdd') + '.jsonl')) -Value ($rec | ConvertTo-Json -Compress -Depth 4) -Encoding UTF8
  } catch { Say "ERROR memory sample: $($_.Exception.Message)" }
}
$lastStress = [datetime]::MinValue; $stressWhy = ''
function StressNow($c) {
  $freeBelow = if ($c.stress -and $c.stress.free_mb_below) { [int]$c.stress.free_mb_below } else { 1000 }
  $commitAbove = if ($c.stress -and $c.stress.commit_pct_above) { [double]$c.stress.commit_pct_above } else { 95 }
  $why = @()
  try { $free = [int]((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1KB); if ($free -lt $freeBelow) { $why += "free $free MB" } } catch {}
  try {
    $os = Get-CimInstance Win32_OperatingSystem
    $cp = [math]::Round(100 * ([double]$os.TotalVirtualMemorySize - [double]$os.FreeVirtualMemory) / [double]$os.TotalVirtualMemorySize, 1)
    if ($cp -gt $commitAbove) { $why += "commit $cp%" }
  } catch {}
  return ($why -join ', ')
}
$match = @{}   # pid -> $true when the target's command-line match applies
$state = @{}   # pid -> 'braked' | 'normal'
while ($true) {
  try {
    $mt = (Get-Item $Config -ErrorAction SilentlyContinue).LastWriteTime
    if ($mt -and $mt -ne $cfgTime) {
      $cfg = Get-Content $Config -Raw | ConvertFrom-Json; $cfgTime = $mt; $match.Clear()
      $on = @($cfg.targets | Where-Object { $_.enabled -and ($protected -notcontains $_.name.ToLower()) } | ForEach-Object { $_.name })
      $off = @($cfg.targets | Where-Object { $_.enabled -and ($protected -contains $_.name.ToLower()) } | ForEach-Object { $_.name })
      Say ("CONFIG loaded: targets on [" + ($on -join ', ') + "]" + $(if ($off.Count) { "; refused as protected [" + ($off -join ', ') + "]" } else { '' }) + "; threads $($cfg.threads) of $n; away after $($cfg.active_window_sec) s")
    }
    if ($cfg) {
      $take = [Math]::Min([int]$cfg.threads, $n)
      $mask = $allMask -band -bnot (([int64]1 -shl ($n - $take)) - 1)
      $wantP = if ([RGB]::IdleSec() -lt [int]$cfg.active_window_sec) { 'braked' } else { 'normal' }
      $hold = if ($cfg.stress -and $cfg.stress.hold_sec) { [int]$cfg.stress.hold_sec } else { 600 }
      if (@($cfg.targets | Where-Object { $_.enabled -and $_.trigger -eq 'stress' }).Count) { $sw = StressNow $cfg; if ($sw) { $lastStress = Get-Date; $stressWhy = $sw } }
      $wantS = if (((Get-Date) - $lastStress).TotalSeconds -lt $hold) { 'braked' } else { 'normal' }
      $targets = @(); $wantOf = @{}
      foreach ($t in @($cfg.targets | Where-Object { $_.enabled -and ($protected -notcontains $_.name.ToLower()) })) {
        $ps = @(Get-Process -Name $t.name -ErrorAction SilentlyContinue)
        if ($ps.Count -eq 0) { continue }
        $mine = @()
        foreach ($p in $ps) {
          if (-not $match.ContainsKey($p.Id)) {
            if ([string]::IsNullOrEmpty($t.match)) { $match[$p.Id] = $true }
            else { $c = (Get-CimInstance Win32_Process -Filter "ProcessId=$($p.Id)" -ErrorAction SilentlyContinue).CommandLine; $match[$p.Id] = ($c -match $t.match) }
          }
          if ($match[$p.Id]) { $mine += $p }
        }
        if ($mine.Count -eq 0) { continue }
        $tw = if ($t.trigger -eq 'stress') { $wantS } else { $wantP }
        foreach ($p in $mine) { $wantOf[$p.Id] = $tw }
        $targets += $mine
        if ($t.helpers) {
          $ids = $mine | ForEach-Object { $_.Id }
          foreach ($hn in $t.helpers) {
            $like = $hn -replace '\*', '%'
            foreach ($h in @(Get-CimInstance Win32_Process -Filter "Name LIKE '$like'" -ErrorAction SilentlyContinue | Where-Object { $ids -contains [int]$_.ParentProcessId })) {
              $hp = Get-Process -Id $h.ProcessId -ErrorAction SilentlyContinue; if ($hp) { $targets += $hp; $wantOf[$hp.Id] = $tw }
            }
          }
        }
      }
      $doneB = @(); $doneR = @()
      foreach ($p in $targets) {
        $want = $wantOf[$p.Id]
        $had = $state.ContainsKey($p.Id)
        $cur = if ($had) { $state[$p.Id] } else { 'normal' }
        if ($cur -ne $want -or -not $had) {
          if ($want -eq 'braked') { $doneB += (Apply $p $true $mask) } elseif ($had) { $doneR += (Apply $p $false $mask) }
          $state[$p.Id] = $want
        }
      }
      $tids = $targets | ForEach-Object { $_.Id }
      foreach ($k in @($state.Keys)) { if ($tids -notcontains $k) { if ($state[$k] -eq 'braked') { $gp = Get-Process -Id $k -ErrorAction SilentlyContinue; if ($gp) { $doneR += (Apply $gp $false $mask) } }; $state.Remove($k) } }
      if ($doneR.Count -gt 0) { Say ("RELEASE (away, calm or target switched off): " + ($doneR -join '; ')) }
      foreach ($k in @($match.Keys)) { if (-not (Get-Process -Id $k -ErrorAction SilentlyContinue)) { $match.Remove($k) } }
      if ($doneB.Count -gt 0) { Say ("BRAKE" + $(if ($stressWhy -and ((Get-Date) - $lastStress).TotalSeconds -lt 60) { " (stress: $stressWhy)" } else { '' }) + ": " + ($doneB -join '; ')) }
      foreach ($k in @($orig.Keys)) { if (-not (Get-Process -Id $k -ErrorAction SilentlyContinue)) { $orig.Remove($k) } }
    }
  } catch { Say "ERROR $($_.Exception.Message)" }
  if (((Get-Date) - $lastMem).TotalSeconds -ge 55) { SampleMem; $lastMem = Get-Date }
  $iv = if ($cfg -and $cfg.interval_sec) { [int]$cfg.interval_sec } else { 30 }
  Start-Sleep -Seconds $iv
}
