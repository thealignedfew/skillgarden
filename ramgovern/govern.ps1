# govern.ps1  ramgovern engine (the Working Set Governor).
#
# Pages idle Claude Code sessions (claude.exe) and, at stage 2, idle VS Code extension hosts out of RAM. A trim is
# OpenProcess(SET_QUOTA|QUERY_INFORMATION) + psapi EmptyWorkingSet: pages go to the standby list, then the compressed store,
# then the pagefile; the process keeps running and faults pages back on demand. Nothing is killed or suspended, so there is
# nothing to undo.
#
#   -Mode task                  fleet sweep (what the scheduled task runs every cadence_minutes)
#   -Mode self -TargetPid N     one named claude.exe, no idle test (the post-turn trim of a session's own process)
#   -Mode seat -TargetPid N     one named process, full idle test
#   -Apply                      trims only when govern.json has enabled=true AND -Apply is passed; otherwise a DRY line
#   -List                       also prints the idle set, oldest first (stdout only, not the log)
#   -ListCode                   prints how every Code.exe is classified and which are eligible hosts, then exits (read-only)
#   -MutexName <name>           the run lock (default Local\RamGovernRun); govern_selfcheck.ps1 uses its own so it
#                               never blocks the scheduled task
#   -IncludeCode                hand runs only (gate tests): treat Code as allowed for this run even at stage 1; the scheduled
#                               task never passes it
#   -Config <path>              settings file (default: govern.json beside this script); govern.state.json and govern.stop
#                               live beside it
#
# Never touched: names in exclusions, the foreground window's process, every process on this run's own ancestor chain (modes
# task and seat), and anything not named claude at stage 1. At stage 2 Code.exe joins, but ONLY the utility processes with
# --utility-sub-type=node.mojom.NodeService (the extension hosts and their siblings), and only after they have shown no CPU
# growth for code_idle_runs x cadence_minutes. Code main, renderers, gpu, network service and crashpad are never trimmed,
# whatever govern.json says.
#
# Design notes (each one came from a failure seen in practice):
#   - Young-process exemption: a process younger than code_min_age_minutes / claude_min_age_minutes is never a candidate. A
#     freshly started extension host trimmed inside its own startup was reported unresponsive.
#   - Daily summary: in task mode the engine writes the daily summary itself, via govern_summary.ps1, once on the first run
#     after 00:05 local time for the previous day (final) and every summary_hour_interval hours for the current day (rolling),
#     guarded by summary_last in govern.state.json.
#   - START line: a task run writes 'task START' at entry with its launch-to-start time, and every APPLY and DRY line ends with
#     'steps-ms enum N summary N select N [trim N prep N sample N]'. A run that stalls or is killed leaves a START line with no
#     matching APPLY line.
#   - Run lock: -Mode task waits up to task_lock_wait_seconds (default 90, 0 = do not wait) for the run lock, because a
#     post-turn self run holds it for about 35 s and an instant exit would lose the task's slot (and a headless console host
#     reports every exit code as 0). Self and seat runs try once. Every lock-busy exit writes
#     '<mode> SKIP: run lock held, waited N ms', and the task START line carries 'lock-wait N ms'.
#   - AI extension hosts: a Code NodeService host that is the parent of a live claude.exe or codex.exe carries an AI coding
#     extension and is never a candidate (counted as 'claudehost N'). Those hosts wake on every scheduled turn of their child
#     sessions; a trim landing just before a burst of turns makes them fault their whole heap back and trips the storm rule.
#   - Storm rule: a trimmed process that climbs above storm_threshold_pct of one core for 10 s within 30 s of its trim is a
#     page-in storm. With storm_action 'stop' the engine writes govern.stop and every later run exits at once (code 3) until a
#     person reads and deletes that file.
#
# Log lines are stamped in the machine's local time with the UTC offset, e.g. '2026-01-15 09:30:00 +01:00'.
# Windows PowerShell 5.1 safe, ASCII only.
[CmdletBinding()]
param(
    [ValidateSet('task', 'self', 'seat')][string]$Mode = 'task',
    [int]$TargetPid = 0,
    [switch]$Apply,
    [switch]$List,
    [switch]$ListCode,
    [switch]$IncludeCode,
    [string]$MutexName = 'Local\RamGovernRun',
    [string]$Config = ''
)
if (-not $Config) { $Config = Join-Path $PSScriptRoot 'govern.json' }

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

$runWatch = [Diagnostics.Stopwatch]::StartNew()
$dir = Split-Path -Parent $Config
$statePath = Join-Path $dir 'govern.state.json'
$stopPath = Join-Path $dir 'govern.stop'

function Get-Stamp([DateTime]$UtcAt = [DateTime]::MinValue) {
    # local time with the real UTC offset, so both passes of the ambiguous fall-back hour stay distinct
    try {
        $tz = $govTz; if ($null -eq $tz) { $tz = [TimeZoneInfo]::Local }
        $utc = [DateTime]::UtcNow; if ($UtcAt -ne [DateTime]::MinValue) { $utc = [DateTime]::SpecifyKind($UtcAt, [DateTimeKind]::Utc) }
        $now = [TimeZoneInfo]::ConvertTimeFromUtc($utc, $tz)
        $off = $tz.GetUtcOffset($utc)
        $sign = '+'; if ($off -lt [TimeSpan]::Zero) { $sign = '-'; $off = $off.Negate() }
        return ('{0:yyyy-MM-dd HH:mm:ss} {1}{2:00}:{3:00}' -f $now, $sign, $off.Hours, $off.Minutes)
    } catch {
        return ('{0:yyyy-MM-dd HH:mm:ss} +00:00' -f [DateTime]::UtcNow)
    }
}
function Get-Cfg($obj, [string]$name, $default) {
    if ($null -ne $obj -and $obj.PSObject.Properties[$name] -and $null -ne $obj.$name) { return $obj.$name }
    return $default
}
function Limit($v, $lo, $hi) { if ($v -lt $lo) { return $lo }; if ($v -gt $hi) { return $hi }; return $v }
function Get-FreeMB { return [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1KB) }
function Get-StartKey($p) { try { return $p.StartTime.ToFileTimeUtc() } catch { return 0 } }
function Get-SentinelPagesIn {
    # optional: newest sample of an external page-in monitor (JSON lines with fields t and pagesIn), named by
    # pagesin_sentinel_pattern, e.g. 'C:\Monitor\samples-{0:yyyyMMdd}.jsonl'; evidence beside CPU in a storm line
    if (-not $sentinelPattern) { return 'n/a' }
    try {
        $f = $sentinelPattern -f (Get-Date)
        $j = Get-Content -Path $f -Tail 1 -ErrorAction Stop | ConvertFrom-Json
        $at = $j.t; if ($at -is [DateTime]) { $at = $at.ToString('HH:mm:ss') }
        return "$($j.pagesIn)/s at $at"
    } catch { return 'n/a' }
}
function Sum-WS($procs) { $s = 0.0; foreach ($p in $procs) { $s += $p.WorkingSet64 }; return [math]::Round($s / 1MB) }

# ---- exit at once when a storm halted the Governor ----
if (Test-Path $stopPath) { Write-Output "govern.stop present at $stopPath; exiting without a run"; exit 3 }

# ---- settings, re-read every run ----
$cfg = $null; $cfgErr = $null
try { $cfg = Get-Content -Raw -Path $Config -ErrorAction Stop | ConvertFrom-Json } catch { $cfgErr = $_.Exception.Message }
$enabled = [bool](Get-Cfg $cfg 'enabled' $false)
$stage = [int](Get-Cfg $cfg 'stage' 1)
$targets = @(Get-Cfg $cfg 'targets' @('claude'))
$idleSec = [int](Limit ([int](Get-Cfg $cfg 'idle_seconds' 10)) 5 300)
$fgGuard = [bool](Get-Cfg $cfg 'foreground_guard' $true)
$recentCpu = [double](Limit ([double](Get-Cfg $cfg 'recent_cpu_seconds' 0.5)) 0 60)
$cadence = [int](Limit ([int](Get-Cfg $cfg 'cadence_minutes' 5)) 1 60)
$exclusions = @(Get-Cfg $cfg 'exclusions' @('Code', 'explorer', 'dwm'))
$codeTypes = @(Get-Cfg $cfg 'code_types' @('utility:NodeService'))
$codeIdleRuns = [int](Limit ([int](Get-Cfg $cfg 'code_idle_runs' 2)) 1 12)
$codeMinAge = [double](Limit ([double](Get-Cfg $cfg 'code_min_age_minutes' 10)) 0 10080)
$claudeMinAge = [double](Limit ([double](Get-Cfg $cfg 'claude_min_age_minutes' 2)) 0 10080)
$sumInterval = [double](Limit ([double](Get-Cfg $cfg 'summary_hour_interval' 1)) 0 24)
$lockWaitSec = [double](Limit ([double](Get-Cfg $cfg 'task_lock_wait_seconds' 90)) 0 280)
$stormPct = [int](Limit ([int](Get-Cfg $cfg 'storm_threshold_pct' 50)) 10 100)
$stormAction = [string](Get-Cfg $cfg 'storm_action' 'stop')
$taskName = [string](Get-Cfg $cfg 'task_name' 'ramgovern')
$sentinelPattern = [string](Get-Cfg $cfg 'pagesin_sentinel_pattern' '')
$logPath = [string](Get-Cfg $cfg 'log_path' '')
if (-not $logPath) { $logPath = Join-Path $dir 'govern.log' }
$logDir = Split-Path -Parent $logPath
if ($logDir -and -not (Test-Path $logDir)) { New-Item -ItemType Directory -Force -Path $logDir | Out-Null }
$govTz = [TimeZoneInfo]::Local

function Write-Log([string]$line) { Add-Content -Path $logPath -Value $line -Encoding ASCII; Write-Output $line }

# Stage 1 reaches claude only. Stage 2 adds Code, and only the kinds listed in $codeKinds below. -IncludeCode switches that
# on for one hand run (gate tests) without touching govern.json.
$allowedByStage = @('claude')
if ($stage -ge 2 -or $IncludeCode.IsPresent) { $allowedByStage = @('claude', 'Code') }
$targetsEff = @($targets); if ($IncludeCode.IsPresent -and ($targetsEff -notcontains 'Code')) { $targetsEff += 'Code' }
$exclEff = @($exclusions); if ($IncludeCode.IsPresent) { $exclEff = @($exclusions | Where-Object { $_ -ne 'Code' }) }
$names = @($targetsEff | Where-Object { ($allowedByStage -contains $_) -and ($exclEff -notcontains $_) })
$codeOn = ($names -contains 'Code')
# the only Code kind the engine will ever trim; code_types can narrow this list, never widen it
$codeKinds = @($codeTypes | Where-Object { $_ -eq 'utility:NodeService' })
$notes = @()
if ($cfgErr) { $notes += "config unreadable ($cfgErr), defaults used" }
if ($stage -gt 2) { $notes += "stage $stage treated as 2" }
if ($IncludeCode.IsPresent) { $notes += 'IncludeCode hand run' }
$stageTag = 'stage1'; if ($codeOn) { $stageTag = 'stage2' }
$doApply = ($Apply.IsPresent -and $enabled -and -not $cfgErr)
if ($Apply.IsPresent -and -not $enabled) { $notes += 'enabled false' }

if (($Mode -ne 'task') -and ($TargetPid -le 0)) { Write-Output "mode $Mode needs -TargetPid"; exit 5 }

# ---- one run at a time ----
$mutex = New-Object System.Threading.Mutex($false, $MutexName)
$haveMutex = $false
$lockSw = [Diagnostics.Stopwatch]::StartNew()
try { $haveMutex = $mutex.WaitOne(0) } catch [System.Threading.AbandonedMutexException] { $haveMutex = $true }
# the task waits (bounded) for a post-turn self run to finish instead of losing its slot; self and seat runs try once
if (-not $haveMutex -and $Mode -eq 'task' -and $lockWaitSec -gt 0) {
    try { $haveMutex = $mutex.WaitOne([int]($lockWaitSec * 1000)) } catch [System.Threading.AbandonedMutexException] { $haveMutex = $true }
}
$lockWaitMs = [math]::Round($lockSw.Elapsed.TotalMilliseconds)
if (-not $haveMutex) {
    # a lock-busy exit leaves a line, so a scheduler that masks exit codes cannot hide a lost run
    try { Write-Log "$(Get-Stamp) $stageTag $Mode SKIP: run lock held, waited $lockWaitMs ms" } catch { }
    Write-Output 'another govern run holds the lock; exiting'; exit 4
}

try {
    # ---- START line at entry (task mode) and the per-step stopwatch ----
    $sw = [Diagnostics.Stopwatch]::StartNew(); $stepMs = [ordered]@{}
    if ($Mode -eq 'task') {
        $launchMs = -1; try { $launchMs = [math]::Round(((Get-Date) - (Get-Process -Id $PID).StartTime).TotalMilliseconds) } catch { }
        Write-Log "$(Get-Stamp) $stageTag task START: pid $PID, launch-to-start $launchMs ms, lock-wait $lockWaitMs ms"
    }
    # ---- state from the previous run ----
    $state = $null
    if (Test-Path $statePath) { try { $state = Get-Content -Raw -Path $statePath | ConvertFrom-Json } catch { $state = $null } }
    $prevCpu = @{}
    if ($state -and $state.procs) { foreach ($e in @($state.procs)) { $prevCpu["$($e.pid)|$($e.start)"] = [double]$e.cpu } }

    # ---- foreground pid and own ancestors ----
    [uint32]$fg = 0
    [void][WsTrim]::GetWindowThreadProcessId([WsTrim]::GetForegroundWindow(), [ref]$fg)
    $ancestors = @{}
    $cur = Get-CimInstance Win32_Process -Filter "ProcessId=$PID"
    for ($i = 0; $i -lt 10 -and $cur; $i++) {
        $ancestors[[int]$cur.ProcessId] = $true   # every process on this run's own chain is off limits (claude.exe or a Code host)
        if (-not $cur.ParentProcessId) { break }
        $cur = Get-CimInstance Win32_Process -Filter "ProcessId=$($cur.ParentProcessId)"
    }

    # ---- Code.exe classification (read-only; the CPU history below is kept for the eligible hosts whatever the stage) ----
    function Get-CodeKind([string]$cl) {
        if ($cl -match '--type=([\w-]+)') { $t = $Matches[1] } else { return 'main' }
        if ($t -eq 'utility') {
            if ($cl -match '--utility-sub-type=([\w\.]+)') {
                $sub = $Matches[1]
                if ($sub -like '*NodeService') { return 'utility:NodeService' }
                if ($sub -like '*NetworkService') { return 'utility:NetworkService' }
            }
            return 'utility:other'
        }
        return $t   # renderer, gpu-process, crashpad-handler, zygote ...
    }
    $codeKind = @{}
    try { Get-CimInstance Win32_Process -Filter "Name='Code.exe'" -ErrorAction Stop | ForEach-Object { $codeKind[[int]$_.ProcessId] = (Get-CodeKind ([string]$_.CommandLine)) } } catch { }
    # a Code host that is the direct parent of a live claude.exe or codex.exe carries an AI coding extension and is never trimmed
    $claudeHostPids = @{}
    try { Get-CimInstance Win32_Process -Filter "Name='claude.exe' OR Name='codex.exe'" -ErrorAction Stop | ForEach-Object { if ($_.ParentProcessId) { $claudeHostPids[[int]$_.ParentProcessId] = $true } } } catch { }
    function Get-CodeEligible {
        if ($codeKind.Count -eq 0) { return @() }
        return @(Get-Process -Name Code -ErrorAction SilentlyContinue | Where-Object { $codeKind.ContainsKey($_.Id) -and ($codeKinds -contains $codeKind[$_.Id]) })
    }
    $codeElig = @(Get-CodeEligible)
    $epochNow = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $qsPrev = @{}
    if ($state -and $state.procs) { foreach ($e in @($state.procs)) { if ($null -ne $e.qs) { $qsPrev["$($e.pid)|$($e.start)"] = [double]$e.qs } } }
    $codeQuietNeed = $codeIdleRuns * $cadence * 60 - 30

    if ($ListCode) {
        Write-Output ("Code.exe processes by kind: " + ((($codeKind.Values | Group-Object | Sort-Object Count -Descending | ForEach-Object { "$($_.Name) $($_.Count)" })) -join ', '))
        Write-Output "Code enabled for this run: $codeOn (stage $stage, quiet needed $codeQuietNeed s)"
        Write-Output 'eligible hosts (pid, started, resident MB, kind, quiet seconds, claudehost = parent of a live claude.exe or codex.exe, never trimmed):'
        foreach ($p in ($codeElig | Sort-Object { try { $_.StartTime } catch { [DateTime]::MaxValue } })) {
            $st = ''; try { $st = $p.StartTime.ToString('yyyy-MM-dd HH:mm:ss') } catch { }
            $k = "$($p.Id)|$(Get-StartKey $p)"; $q = 'none'; if ($qsPrev.ContainsKey($k)) { $q = [string]([math]::Max(0, $epochNow - [long]$qsPrev[$k])) }
            $ch = 'no'; if ($claudeHostPids.ContainsKey([int]$p.Id)) { $ch = 'claudehost' }
            Write-Output ('  {0,7}  {1}  {2,6}  {3}  {4}  {5}' -f $p.Id, $st, [math]::Round($p.WorkingSet64 / 1MB), $codeKind[$p.Id], $q, $ch)
        }
        exit 0
    }

    $nameStr = ($names -join ',')
    $all = @()
    $claudeNames = @($names | Where-Object { $_ -ne 'Code' })
    if ($claudeNames.Count -gt 0) { $all = @(Get-Process -Name $claudeNames -ErrorAction SilentlyContinue) }
    if ($codeOn) { $all = @($all) + @($codeElig) }
    $nAll = $all.Count

    # ---- cadence mismatch (task mode only) ----
    if ($Mode -eq 'task') {
        try {
            $tk = Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
            $iv = $tk.Triggers[0].Repetition.Interval
            if ($iv) {
                $mins = [System.Xml.XmlConvert]::ToTimeSpan($iv).TotalMinutes
                if ([math]::Round($mins) -ne $cadence) { $notes += "MISMATCH cadence_minutes $cadence vs task trigger $([math]::Round($mins))" }
            }
        } catch { }
    }

    # ---- regrow at next run: the pids the previous task run trimmed, resident now against their 30 s figure ----
    $regrow = 'regrow-since-last none'
    if ($Mode -eq 'task' -and $state -and $state.last_trim) {
        $byId = @{}; foreach ($p in $all) { $byId["$($p.Id)|$(Get-StartKey $p)"] = $p }
        $n = 0; $w30 = 0.0; $wnow = 0.0
        foreach ($e in @($state.last_trim)) {
            $k = "$($e.pid)|$($e.start)"
            if ($byId.ContainsKey($k)) { $n++; $w30 += [double]$e.ws30; $wnow += ($byId[$k].WorkingSet64 / 1MB) }
        }
        if ($n -gt 0) { $regrow = "regrow-since-last $([math]::Round($wnow)) MB vs $([math]::Round($w30)) MB at 30 s for $n pids" }
    }

    $stepMs.enum = $sw.ElapsedMilliseconds; $sw.Restart()
    # ---- daily summary from inside the task: never allowed to delay or block a trim ----
    $summaryLast = @{ final_for = ''; rolling_at = [long]0 }
    if ($state -and $state.summary_last) {
        try {
            if ($state.summary_last.final_for) { $summaryLast.final_for = [string]$state.summary_last.final_for }
            if ($state.summary_last.rolling_at) { $summaryLast.rolling_at = [long]$state.summary_last.rolling_at }
        } catch { }
    }
    if ($Mode -eq 'task' -and $sumInterval -gt 0) {
        try {
            $nowL = [TimeZoneInfo]::ConvertTimeFromUtc([DateTime]::UtcNow, $govTz)
            $todayL = $nowL.ToString('yyyy-MM-dd'); $yestL = $nowL.AddDays(-1).ToString('yyyy-MM-dd')
            $sumScript = Join-Path $PSScriptRoot 'govern_summary.ps1'
            $sumJobs = @()
            if ((($nowL.Hour * 60 + $nowL.Minute) -ge 5) -and ($summaryLast.final_for -ne $yestL)) { $sumJobs += @{ date = $yestL; kind = 'final' } }
            if (($epochNow - $summaryLast.rolling_at) -ge ($sumInterval * 3600 - 60)) { $sumJobs += @{ date = $todayL; kind = 'rolling' } }
            foreach ($j in $sumJobs) {
                $res = (& $sumScript -Date $j.date -Config $Config 2>&1 | Select-Object -Last 1)
                Write-Log "$(Get-Stamp) $stageTag task summary $($j.kind) $($j.date): $res"
                if ($j.kind -eq 'final') { $summaryLast.final_for = $j.date } else { $summaryLast.rolling_at = [long]$epochNow }
            }
        } catch { $notes += "summary error: $($_.Exception.Message)" }
    }

    $stepMs.summary = $sw.ElapsedMilliseconds; $sw.Restart()
    # ---- candidates ----
    $cand = $all
    if ($Mode -ne 'task') {
        if ($Mode -eq 'self' -and $codeKind.ContainsKey($TargetPid)) {
            Write-Log "$(Get-Stamp) $stageTag $Mode REFUSED: pid $TargetPid is Code.exe; self mode is for a session's own claude.exe only; nothing trimmed"
            exit 6
        }
        $cand = @($all | Where-Object { $_.Id -eq $TargetPid })
        if ($cand.Count -eq 0) {
            $why = "is not a running process named $nameStr (or is excluded)"
            if ($codeKind.ContainsKey($TargetPid)) {
                if ($codeOn) { $why = "is Code.exe of kind $($codeKind[$TargetPid]), which is never trimmed" } else { $why = "is Code.exe of kind $($codeKind[$TargetPid]), and Code is not enabled for this run" }
            }
            Write-Log "$(Get-Stamp) $stageTag $Mode REFUSED: pid $TargetPid $why; nothing trimmed"
            exit 6
        }
    }

    # ---- idle test ----
    $cpuA = @{}; foreach ($p in $cand) { $cpuA[$p.Id] = @{ cpu = [double]$p.CPU; start = (Get-StartKey $p) } }
    if ($Mode -ne 'self') { Start-Sleep -Seconds $idleSec }
    $now = @{}
    if ($cand.Count -gt 0) { Get-Process -Name $names -ErrorAction SilentlyContinue | ForEach-Object { $now[$_.Id] = $_ } }
    $skip = @{ fg = 0; recent = 0; own = 0; busy = 0; gone = 0; quiet = 0; young = 0; claudehost = 0 }
    $idle = New-Object System.Collections.ArrayList
    foreach ($p in $cand) {
        $id = $p.Id
        if (-not $now.ContainsKey($id) -or (Get-StartKey $now[$id]) -ne $cpuA[$id].start) { $skip.gone++; continue }
        $q = $now[$id]
        if ($fgGuard -and [uint32]$id -eq $fg) { $skip.fg++; continue }
        if ($codeKind.ContainsKey($id) -and $claudeHostPids.ContainsKey([int]$id)) { $skip.claudehost++; continue }
        $minAge = $claudeMinAge; if ($codeKind.ContainsKey($id)) { $minAge = $codeMinAge }
        if ($minAge -gt 0) {
            $ageMin = $null; try { $ageMin = ((Get-Date) - $q.StartTime).TotalMinutes } catch { }
            if ($null -ne $ageMin -and $ageMin -lt $minAge) { $skip.young++; continue }
        }
        if ($Mode -eq 'self') { [void]$idle.Add($q); continue }
        if ($ancestors.ContainsKey([int]$id)) { $skip.own++; continue }
        $c1 = [double]$q.CPU
        if (($c1 - $cpuA[$id].cpu) -ge 0.05) { $skip.busy++; continue }
        if ($codeKind.ContainsKey($id)) {
            # a Code host needs a quiet history, not just a quiet 10 s: the host of the window the user is typing in serves keystrokes
            $kq = "$id|$($cpuA[$id].start)"
            if (-not $qsPrev.ContainsKey($kq) -or (($epochNow - [long]$qsPrev[$kq]) -lt $codeQuietNeed)) { $skip.quiet++; continue }
        }
        if ($fgGuard) {
            $k = "$id|$($cpuA[$id].start)"
            if ($prevCpu.ContainsKey($k) -and (($c1 - $prevCpu[$k]) -gt $recentCpu)) { $skip.recent++; continue }
        }
        [void]$idle.Add($q)
    }
    $nIdle = $idle.Count
    $ws0 = Sum-WS $idle
    $free0 = Get-FreeMB
    $skipTxt = "skipped fg $($skip.fg) recent $($skip.recent) busy $($skip.busy) own $($skip.own)"
    $codeIdle = @($idle | Where-Object { $codeKind.ContainsKey($_.Id) })
    $codeNote = $null
    $skipYoung = " young $($skip.young)"
    if ($codeOn) { $skipTxt += " quiet $($skip.quiet)"; $codeNote = "code idle $($codeIdle.Count) of $($codeElig.Count) hosts, resident $(Sum-WS $codeIdle) MB" }
    $skipTxt += $skipYoung
    if ($codeOn) { $skipTxt += " claudehost $($skip.claudehost)" }
    function Save-State($trimList) {
        $nowAll = @(); if ($claudeNames.Count -gt 0) { $nowAll = @(Get-Process -Name $claudeNames -ErrorAction SilentlyContinue) }
        $nowAll = @($nowAll) + @(Get-CodeEligible)   # Code hosts are tracked (CPU only) at every stage so their quiet history exists when stage 2 starts
        $nowE = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
        $prevE = @{}
        if ($state -and $state.procs) { foreach ($e in @($state.procs)) { $qv = $nowE; if ($null -ne $e.qs) { $qv = [long]$e.qs }; $prevE["$($e.pid)|$($e.start)"] = @{ cpu = [double]$e.cpu; qs = $qv } } }
        $fresh = @{}
        foreach ($p in $nowAll) {
            $k = "$($p.Id)|$(Get-StartKey $p)"
            $c = [math]::Round([double]$p.CPU, 3)
            $qs = $nowE
            if ($prevE.ContainsKey($k)) { if (($c - $prevE[$k].cpu) -le $recentCpu) { $qs = $prevE[$k].qs } }
            $fresh[$k] = @{ cpu = $c; qs = $qs }
        }
        $merged = @{}
        if ($Mode -eq 'task') { foreach ($k in $fresh.Keys) { $merged[$k] = $fresh[$k] } }
        else {
            # seat and self runs refresh only the pids they touched; every other baseline keeps its previous-run value
            foreach ($k in $prevE.Keys) { if ($fresh.ContainsKey($k)) { $merged[$k] = $prevE[$k] } }
            foreach ($p in $cand) { $k = "$($p.Id)|$(Get-StartKey $p)"; if ($fresh.ContainsKey($k)) { $merged[$k] = $fresh[$k] } }
            foreach ($k in $fresh.Keys) { if (-not $merged.ContainsKey($k)) { $merged[$k] = $fresh[$k] } }
        }
        $procs = @()
        foreach ($k in $merged.Keys) { $a = $k.Split('|'); $procs += @{ pid = [int]$a[0]; start = [int64]$a[1]; cpu = $merged[$k].cpu; qs = [long]$merged[$k].qs } }
        $lt = @()
        if ($Mode -eq 'task') { $lt = $trimList }
        elseif ($state -and $state.last_trim) { $lt = @($state.last_trim) }
        $obj = @{ updated = (Get-Stamp); mode = $Mode; procs = $procs; last_trim = $lt; summary_last = $summaryLast }
        ($obj | ConvertTo-Json -Depth 5) | Set-Content -Path $statePath -Encoding ASCII
    }

    if ($Mode -ne 'task' -and $nIdle -eq 0) {
        Write-Log "$(Get-Stamp) $stageTag $Mode SKIPPED: pid $TargetPid not trimmed ($skipTxt); free $free0 MB; run $([math]::Round($runWatch.Elapsed.TotalSeconds)) s"
        Save-State @()
        exit 7
    }

    if ($List) {
        Write-Output "idle set, oldest first (pid, started, resident MB, kind):"
        $idle | Sort-Object { try { $_.StartTime } catch { [DateTime]::MaxValue } } | ForEach-Object {
            $st = ''; try { $st = $_.StartTime.ToString('yyyy-MM-dd HH:mm:ss') } catch { }
            $kd = 'claude'; if ($codeKind.ContainsKey($_.Id)) { $kd = "Code $($codeKind[$_.Id])" }
            Write-Output ('  {0,7}  {1}  {2,6}  {3}' -f $_.Id, $st, [math]::Round($_.WorkingSet64 / 1MB), $kd)
        }
    }

    $extras = @($regrow, $skipTxt, $codeNote) + $notes | Where-Object { $_ }

    $stepMs.select = $sw.ElapsedMilliseconds; $sw.Restart()
    # ---- dry run ----
    if (-not $doApply) {
        $extras = @($extras) + "steps-ms enum $($stepMs.enum) summary $($stepMs.summary) select $($stepMs.select)"
        $line = "$(Get-Stamp) $stageTag $Mode DRY: $nIdle idle of $nAll $nameStr; resident $ws0 MB; free $free0 MB; storm n/a; failed 0; 0 ms; $($extras -join '; '); run $([math]::Round($runWatch.Elapsed.TotalSeconds)) s"
        Write-Log $line
        Save-State @()
        exit 0
    }

    # ---- trim ----
    $trimmed = New-Object System.Collections.ArrayList
    $fail = 0; $failCodes = @()
    $t0 = Get-Date
    foreach ($q in $idle) {
        if ($codeKind.ContainsKey($q.Id) -and ($codeKinds -notcontains $codeKind[$q.Id])) { continue }   # never reached; a Code kind outside the allowed list is not trimmed
        $r = [WsTrim]::Trim($q.Id)
        if ($r -eq 0) { [void]$trimmed.Add($q) } else { $fail++; $failCodes += $r }
    }
    $trimMs = [math]::Round(((Get-Date) - $t0).TotalMilliseconds)
    $sw.Restart()
    $ids = @($trimmed | ForEach-Object { $_.Id })

    $pc = $null; try { $pc = New-Object System.Diagnostics.PerformanceCounter('Memory', 'Pages Input/sec'); [void]$pc.NextValue() } catch { $pc = $null }
    $cpuT = @{}; $startOf = @{}
    if ($ids.Count -gt 0) { Get-Process -Id $ids -ErrorAction SilentlyContinue | ForEach-Object { $cpuT[$_.Id] = [double]$_.CPU; $startOf[$_.Id] = (Get-StartKey $_) } }
    $samples = New-Object System.Collections.ArrayList
    [void]$samples.Add(@{ t = 0.0; cpu = $cpuT })
    $stepMs.prep = $sw.ElapsedMilliseconds
    $w = [Diagnostics.Stopwatch]::StartNew()
    $ws2 = 0; $free2 = 0; $pagesMax = 0; $storm = $null; $curProcs = @{}
    $thr = $stormPct / 100.0
    for ($i = 1; $i -le 15; $i++) {
        Start-Sleep -Seconds 2
        $t = $w.Elapsed.TotalSeconds
        $curProcs = @{}
        if ($ids.Count -gt 0) { Get-Process -Id $ids -ErrorAction SilentlyContinue | ForEach-Object { $curProcs[$_.Id] = $_ } }
        if ($i -eq 1) { $ws2 = Sum-WS $curProcs.Values; $free2 = Get-FreeMB }
        if ($pc) { try { $v = [math]::Round($pc.NextValue()); if ($v -gt $pagesMax) { $pagesMax = $v } } catch { } }
        $cpuNow = @{}; foreach ($k in $curProcs.Keys) { $cpuNow[$k] = [double]$curProcs[$k].CPU }
        if ($t -ge 10 -and -not $storm) {
            $base = $null
            foreach ($s in $samples) { if ($s.t -le ($t - 10)) { $base = $s } }
            if ($base) {
                $win = $t - $base.t
                foreach ($k in $cpuNow.Keys) {
                    if ($base.cpu.ContainsKey($k)) {
                        $d = $cpuNow[$k] - $base.cpu[$k]
                        if ($d -ge ($thr * $win)) { $storm = @{ pid = $k; cpu = [math]::Round($d, 2); win = [math]::Round($win, 1) }; break }
                    }
                }
            }
        }
        [void]$samples.Add(@{ t = $t; cpu = $cpuNow })
        if ($storm -and $stormAction -eq 'stop') { break }
    }
    $stepMs.sample = [math]::Round($w.Elapsed.TotalMilliseconds)
    $ws30 = Sum-WS $curProcs.Values
    $free30 = Get-FreeMB
    $cpuWithin = 0
    foreach ($k in $curProcs.Keys) { if ($cpuT.ContainsKey($k) -and (([double]$curProcs[$k].CPU - $cpuT[$k]) -gt 0.05)) { $cpuWithin++ } }

    $stormTxt = 'none'
    $sentinel = Get-SentinelPagesIn
    if ($storm) { $stormTxt = "pid $($storm.pid) $($storm.cpu) cpu-s in $($storm.win) s, sentinel pagesIn $sentinel, own pagesin-max $pagesMax/s" }
    if ($storm -and $stormAction -eq 'stop') {
        $stopObj = @{ at = (Get-Stamp); pid = $storm.pid; cpu_seconds = $storm.cpu; window_seconds = $storm.win; pagesin_max = $pagesMax; sentinel_pagesin = $sentinel; action = 'stop' }
        ($stopObj | ConvertTo-Json) | Set-Content -Path $stopPath -Encoding ASCII
        $stormTxt += ' HALTED govern.stop written'
    }
    $failTxt = "$fail"; if ($fail -gt 0) { $failTxt = "$fail (codes $((($failCodes | Select-Object -Unique) -join ',')))" }
    $codeNote2 = $null
    if ($codeOn) {
        $cT = @($trimmed | Where-Object { $codeKind.ContainsKey($_.Id) })
        $cLive = @($curProcs.Values | Where-Object { $codeKind.ContainsKey($_.Id) })
        $codeNote2 = "code trimmed $($cT.Count) of $($codeIdle.Count) idle, resident $(Sum-WS $codeIdle) -> $(Sum-WS $cLive) MB at 30 s"
    }
    $extras = @($regrow, $skipTxt, $codeNote2, "pagesin-max $pagesMax/s", "sentinel pagesIn $sentinel", "steps-ms enum $($stepMs.enum) summary $($stepMs.summary) select $($stepMs.select) trim $trimMs prep $($stepMs.prep) sample $($stepMs.sample)") + $notes | Where-Object { $_ }
    $line = "$(Get-Stamp) $stageTag $Mode APPLY: $nIdle idle of $nAll $nameStr; resident $ws0 -> $ws2 (2s) -> $ws30 (30s) MB; free $free0 -> $free2 -> $free30 MB; cpu-within-30s $cpuWithin of $($trimmed.Count); storm $stormTxt; failed $failTxt; $trimMs ms; $($extras -join '; '); run $([math]::Round($runWatch.Elapsed.TotalSeconds)) s"
    Write-Log $line

    $lt = @(); foreach ($k in $curProcs.Keys) { $lt += @{ pid = $k; start = $startOf[$k]; ws30 = [math]::Round($curProcs[$k].WorkingSet64 / 1MB, 1) } }
    Save-State $lt
    if ($storm -and $stormAction -eq 'stop') { exit 2 }
    exit 0
}
catch {
    try { Write-Log "$(Get-Stamp) $stageTag $Mode ERROR: $($_.Exception.Message) at line $($_.InvocationInfo.ScriptLineNumber); nothing further trimmed" } catch { }
    exit 1
}
finally {
    if ($haveMutex) { try { $mutex.ReleaseMutex() } catch { } }
}
