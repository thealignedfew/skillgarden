# govern_selfcheck.ps1  Pester-free check of govern.ps1. Run it after any engine edit.
# Runs against a temp copy of the settings (own log, state and stop file) so the real govern.log, govern.state.json and
# govern.stop are never touched, and with enabled=false so nothing is ever trimmed. -Engine tests a copy before it is swapped in.
# Asserts:
#   1 and 2  -Mode task as a dry run, twice: each exits 0 and appends one 'task DRY:' line with the UTC offset
#   3        -Mode task -Apply with enabled=false: still a DRY line, nothing trimmed
#   4        govern.stop present: exits 3 and writes no line
#   5        stage 1: Code is not enabled (-ListCode says so) and the dry line carries no Code counts
#   6        stage 2: Code is enabled and the eligible hosts are exactly Code.exe utility NodeService processes, checked against an
#            independent query of each command line (no renderer, main, gpu, network service or crashpad ever listed)
#   7        stage 2 dry run: the line carries the Code counts and the -List rows for Code are all utility:NodeService
#   8        stage 2 with Code in exclusions: Code is not enabled
#   9        -Mode self on a Code process and -Mode seat on a Code renderer and on a Code main are refused, nothing trimmed
#   10       a seat run that skips its target (an ancestor claude.exe) writes one SKIPPED line, exits 7, and no ERROR line
#   11       young-process exemption: minimum age at a week leaves no candidates and the line reports young; age 0 turns it off
#   12       summary from inside the task: first run writes the due summaries, an immediate second run none, interval 0 none
#   13       a task run writes a 'task START' line before its DRY line, and the DRY line ends with 'steps-ms enum N summary N select N'
#   14       the stamp carries the real UTC offset, including both passes of the ambiguous fall-back hour (02:30 +02:00, then 02:30 +01:00),
#            checked in a fixed zone (Central European) so the expected values do not depend on the machine's own zone
#   15       with the run lock held by the self-check, a task run with a 2 s wait exits 4 and logs 'task SKIP: run lock held, waited N ms' (N >= 1900),
#            a self run exits 4 and logs 'self SKIP', a task run with a 0 s wait does not wait, and a task run whose lock is released mid-wait goes on to a
#            DRY line with 'lock-wait N ms' on its START line
#   16       a Code NodeService host that is the direct parent of a live claude.exe or codex.exe is never a candidate: -ListCode marks exactly the hosts
#            an independent parent query finds, the stage 2 dry line reports 'claudehost N' with that count, and none of the marked pids appears among the
#            candidate rows of -Mode task -List. Dry runs only (enabled=false), so nothing is ever trimmed by this case.
# Exit code 0 = all passed, 1 = a failure. Takes a few minutes (idle_seconds 5; longer on a machine short of memory).
param([string]$Engine = '')
$ErrorActionPreference = 'Stop'
if (-not $Engine) { $Engine = Join-Path $PSScriptRoot 'govern.ps1' }
$tmp = Join-Path $env:TEMP ('govern_selfcheck_' + [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
$cfgPath = Join-Path $tmp 'govern.json'
$logPath = Join-Path $tmp 'govern.log'
$real = Get-Content -Raw (Join-Path $PSScriptRoot 'govern.json') | ConvertFrom-Json
function Write-Cfg([int]$stage, [string[]]$targets, [string[]]$excl, [hashtable]$extra = @{}) {
    $c = $real.PSObject.Copy()
    $c.enabled = $false; $c.idle_seconds = 5; $c.log_path = $logPath; $c.stage = $stage; $c.targets = $targets; $c.exclusions = $excl
    Add-Member -InputObject $c -NotePropertyName summary_hour_interval -NotePropertyValue 0 -Force   # off unless a case turns it on, so line counts stay exact
    foreach ($k in $extra.Keys) { Add-Member -InputObject $c -NotePropertyName $k -NotePropertyValue $extra[$k] -Force }
    ($c | ConvertTo-Json -Depth 5) | Set-Content -Path $cfgPath -Encoding ASCII
}
Write-Cfg 1 @('claude') @('Code', 'explorer', 'dwm')

$fails = 0
function Assert([bool]$cond, [string]$msg) {
    if ($cond) { Write-Output "PASS  $msg" } else { Write-Output "FAIL  $msg"; $script:fails++ }
}
$hasMutexParam = (Get-Content -Raw $Engine) -match 'MutexName'
function Run-Engine([string[]]$extra) {
    if ($hasMutexParam) { $extra = @('-MutexName', 'Local\RamGovernSelfcheck') + $extra }   # its own lock: never blocks, or waits for, the scheduled task
    $out = & powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $Engine -Config $cfgPath @extra 2>&1
    return @{ code = $LASTEXITCODE; out = ($out -join "`n") }
}
function Line-Count { if (Test-Path $logPath) { return @(Get-Content $logPath).Count } else { return 0 } }
$zoneRx = '^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d [+-]\d\d:\d\d stage\d task DRY: '
$engineText = Get-Content -Raw $Engine
$hasStart = $engineText -match 'task START'
$perRun = 1; if ($hasStart) { $perRun = 2 }   # a task run writes its START line and then its DRY or APPLY line
$startRx = '^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d [+-]\d\d:\d\d stage\d task START: pid \d+, launch-to-start -?\d+ ms, lock-wait \d+ ms$'

for ($n = 1; $n -le 2; $n++) {
    $before = Line-Count
    $r = Run-Engine @('-Mode', 'task')
    $after = Line-Count
    $last = ''; if (Test-Path $logPath) { $last = (Get-Content $logPath | Select-Object -Last 1) }
    Assert ($r.code -eq 0) "dry run $n exits 0 (got $($r.code))"
    Assert (($after - $before) -eq $perRun) "dry run $n wrote exactly $perRun log line(s)"
    Assert ($last -match $zoneRx) "dry run $n line is a task DRY line with a local stamp and UTC offset: $last"
}

$before = Line-Count
$r = Run-Engine @('-Mode', 'task', '-Apply')
$last = (Get-Content $logPath | Select-Object -Last 1)
Assert ($r.code -eq 0 -and (Line-Count) -eq ($before + $perRun)) "task -Apply with enabled=false writes $perRun line(s) and exits 0"
Assert ($last -match 'task DRY: ' -and $last -match 'enabled false' -and $last -notmatch ' APPLY: ') 'enabled=false stays DRY and says so'

'{"test":true}' | Set-Content -Path (Join-Path $tmp 'govern.stop') -Encoding ASCII
$before = Line-Count
$r = Run-Engine @('-Mode', 'task')
Assert ($r.code -eq 3 -and (Line-Count) -eq $before) "govern.stop present: exit 3 and no log line (exit $($r.code))"
Remove-Item (Join-Path $tmp 'govern.stop') -Force

# ---- Code cases ----
$codeCim = @(Get-CimInstance Win32_Process -Filter "Name='Code.exe'" | ForEach-Object { [pscustomobject]@{ pid = [int]$_.ProcessId; cl = [string]$_.CommandLine } })
$nodePids = @($codeCim | Where-Object { $_.cl -match '--type=utility' -and $_.cl -match '--utility-sub-type=node\.mojom\.NodeService' } | ForEach-Object { $_.pid })
$renderer = @($codeCim | Where-Object { $_.cl -match '--type=renderer' } | Select-Object -First 1)
$main = @($codeCim | Where-Object { $_.cl -notmatch '--type=' } | Select-Object -First 1)

# 5 stage 1
$r = Run-Engine @('-ListCode')
Assert ($r.out -match 'Code enabled for this run: False') 'stage 1: -ListCode says Code is not enabled'
$before = Line-Count
$r = Run-Engine @('-Mode', 'task'); $last = (Get-Content $logPath | Select-Object -Last 1)
Assert ($last -match 'stage1 task DRY' -and $last -notmatch 'code idle') 'stage 1 dry line is stage1 and carries no Code counts'

# 6 and 7 stage 2
Write-Cfg 2 @('claude', 'Code') @('explorer', 'dwm')
$r = Run-Engine @('-ListCode')
Assert ($r.out -match 'Code enabled for this run: True') 'stage 2: -ListCode says Code is enabled'
$elig = @($r.out -split "`n" | Where-Object { $_ -match '^\s+\d+\s+\d{4}-\d\d-\d\d' } | ForEach-Object { [int](($_.Trim() -split '\s+')[0]) })
$bad = @($elig | Where-Object { $nodePids -notcontains $_ })
Assert ($elig.Count -ge 1 -and $bad.Count -eq 0) "stage 2: every eligible Code host ($($elig.Count)) is a utility NodeService by an independent command-line check; $($bad.Count) are not"
$rend = @($codeCim | Where-Object { $_.cl -match '--type=renderer|--type=gpu-process|--type=crashpad|--utility-sub-type=network\.mojom\.NetworkService' -or $_.cl -notmatch '--type=' } | ForEach-Object { $_.pid })
$leak = @($elig | Where-Object { $rend -contains $_ })
Assert ($leak.Count -eq 0) "stage 2: no renderer, main, gpu, network service or crashpad pid is eligible ($($leak.Count) leaked)"
$r = Run-Engine @('-Mode', 'task', '-List'); $last = (Get-Content $logPath | Select-Object -Last 1)
Assert ($last -match 'stage2 task DRY' -and $last -match 'code idle \d+ of \d+ hosts') 'stage 2 dry line is stage2 and carries the Code counts'
$rows = @($r.out -split "`n" | Where-Object { $_ -match '^\s+\d+\s+\d{4}-.*Code ' })
$badRows = @($rows | Where-Object { $_ -notmatch 'Code utility:NodeService\s*$' })
Assert ($badRows.Count -eq 0) "stage 2 -List: all $($rows.Count) Code rows are utility:NodeService"

# 8 exclusions win
Write-Cfg 2 @('claude', 'Code') @('Code', 'explorer', 'dwm')
$r = Run-Engine @('-ListCode')
Assert ($r.out -match 'Code enabled for this run: False') 'stage 2 with Code in exclusions: Code is not enabled'

# 9 refusals, at stage 2
Write-Cfg 2 @('claude', 'Code') @('explorer', 'dwm')
if ($nodePids.Count -ge 1) {
    $r = Run-Engine @('-Mode', 'self', '-TargetPid', "$($nodePids[0])", '-Apply'); $last = (Get-Content $logPath | Select-Object -Last 1)
    Assert ($r.code -eq 6 -and $last -match 'self REFUSED' -and $last -notmatch ' APPLY: ') 'self mode on a Code process is refused'
}
if ($renderer.Count -ge 1) {
    $r = Run-Engine @('-Mode', 'seat', '-TargetPid', "$($renderer[0].pid)", '-Apply'); $last = (Get-Content $logPath | Select-Object -Last 1)
    Assert ($r.code -eq 6 -and $last -match 'REFUSED' -and $last -match 'renderer' -and $last -notmatch ' APPLY: ') 'seat mode on a Code renderer is refused'
}
if ($main.Count -ge 1) {
    $r = Run-Engine @('-Mode', 'seat', '-TargetPid', "$($main[0].pid)", '-Apply'); $last = (Get-Content $logPath | Select-Object -Last 1)
    Assert ($r.code -eq 6 -and $last -match 'REFUSED' -and $last -match 'main' -and $last -notmatch ' APPLY: ') 'seat mode on the Code main process is refused'
}

# 10 a seat run that skips its target (here: the claude.exe this check runs under, an ancestor) logs one SKIPPED line and nothing else
Write-Cfg 1 @('claude') @('Code', 'explorer', 'dwm')
$anc = 0; $cur = Get-CimInstance Win32_Process -Filter "ProcessId=$PID"
for ($i = 0; $i -lt 10 -and $cur; $i++) { if ($cur.Name -eq 'claude.exe') { $anc = [int]$cur.ProcessId; break }; if (-not $cur.ParentProcessId) { break }; $cur = Get-CimInstance Win32_Process -Filter "ProcessId=$($cur.ParentProcessId)" }
if ($anc -gt 0) {
    $before = Line-Count
    $r = Run-Engine @('-Mode', 'seat', '-TargetPid', "$anc"); $last = (Get-Content $logPath | Select-Object -Last 1)
    Assert ($r.code -eq 7 -and (Line-Count) -eq ($before + 1) -and $last -match 'seat SKIPPED' -and $last -notmatch 'ERROR') "seat run that skips its target logs one SKIPPED line, exit 7, no ERROR (exit $($r.code))"
} else { Write-Output 'SKIP  no claude.exe ancestor found; skipped-seat case not run' }

# 11 young-process exemption: with the minimum age at its ceiling (a week) every process counts as young, so nothing is
#    idle, the line says how many were skipped as young, and the default (no key) leaves the normal behavior alone
$hasYoung = (Get-Content -Raw $Engine) -match 'claude_min_age_minutes'
if ($hasYoung) {
    Write-Cfg 2 @('claude', 'Code') @('explorer', 'dwm') @{ claude_min_age_minutes = 10080; code_min_age_minutes = 10080 }
    $r = Run-Engine @('-Mode', 'task'); $last = (Get-Content $logPath | Select-Object -Last 1)
    Assert ($last -match 'task DRY: 0 idle of' -and $last -match ' young [1-9]\d*' -and $last -match 'code idle 0 of') "young-process exemption: with minimum age at a week nothing is a candidate and the line reports young: $($last.Substring(0, [math]::Min(190, $last.Length)))"
    Write-Cfg 2 @('claude', 'Code') @('explorer', 'dwm') @{ claude_min_age_minutes = 0; code_min_age_minutes = 0 }
    $r = Run-Engine @('-Mode', 'task'); $last = (Get-Content $logPath | Select-Object -Last 1)
    Assert ($last -match ' young 0' -and $last -notmatch 'task DRY: 0 idle of') 'minimum age 0 turns the exemption off: young 0 and candidates remain'
    Write-Cfg 1 @('claude') @('Code', 'explorer', 'dwm')
    $r = Run-Engine @('-Mode', 'task'); $last = (Get-Content $logPath | Select-Object -Last 1)
    Assert ($last -match ' young \d+') 'default settings: every dry line carries the young count'
} else { Write-Output 'SKIP  engine has no young-process exemption; case 11 not run' }

# 12 daily summary from inside the task: the first task run writes the due summaries (final for yesterday after 00:05, rolling
#    for today) and one 'task summary' line each; an immediate second run writes nothing (the stamp guards it); interval 0 turns it off
if ((Get-Content -Raw $Engine) -match 'summary_hour_interval') {
    function Sum-Lines { if (Test-Path $logPath) { return @(Get-Content $logPath | Where-Object { $_ -match ' task summary ' }).Count } else { return 0 } }
    Write-Cfg 1 @('claude') @('Code', 'explorer', 'dwm') @{ summary_hour_interval = 1 }
    $b = Sum-Lines; $r = Run-Engine @('-Mode', 'task'); $a1 = Sum-Lines
    Assert (($a1 - $b) -ge 1) "summary: the first task run wrote $($a1 - $b) summary line(s)"
    $todayFile = Join-Path $tmp ('summary-{0}.md' -f (Get-Date -Format 'yyyyMMdd'))
    Assert (Test-Path $todayFile) 'summary: the rolling summary file for today exists beside the settings'
    $r = Run-Engine @('-Mode', 'task'); $a2 = Sum-Lines
    Assert ($a2 -eq $a1) "summary: an immediate second run wrote none ($($a2 - $a1) new), the stamp guards it"
    Write-Cfg 1 @('claude') @('Code', 'explorer', 'dwm') @{ summary_hour_interval = 0 }
    Remove-Item (Join-Path $tmp 'govern.state.json') -Force -ErrorAction SilentlyContinue
    $r = Run-Engine @('-Mode', 'task'); $a3 = Sum-Lines
    Assert ($a3 -eq $a2) "summary: interval 0 writes none even with no stamp ($($a3 - $a2) new)"
} else { Write-Output 'SKIP  engine has no summary step; case 12 not run' }

# 13 START line and per-step timing
if ($hasStart) {
    Write-Cfg 1 @('claude') @('Code', 'explorer', 'dwm')
    $before = Line-Count
    $r = Run-Engine @('-Mode', 'task')
    $tail = @(Get-Content $logPath | Select-Object -Last 2)
    Assert ($tail.Count -eq 2 -and $tail[0] -match $startRx) "START line precedes the run's own line: $($tail[0])"
    Assert ($tail[1] -match 'task DRY: ' -and $tail[1] -match 'steps-ms enum \d+ summary \d+ select \d+') 'the DRY line ends its extras with steps-ms enum, summary and select'
    $before = Line-Count
    $r = Run-Engine @('-Mode', 'self', '-TargetPid', "$PID")
    $selfNew = @(Get-Content $logPath | Select-Object -Skip $before)
    Assert (-not ($selfNew | Where-Object { $_ -match ' START' })) 'self mode writes no START line'
} else { Write-Output 'SKIP  engine has no START line; case 13 not run' }

# 14 the UTC offset in the stamp, fed to the engine's own Get-Stamp by instant in a fixed zone
if ($engineText -match 'UtcAt') {
    $tk = $null; $er = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($Engine, [ref]$tk, [ref]$er)
    $fn = $ast.Find({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Get-Stamp' }, $true)
    Invoke-Expression $fn.Extent.Text
    $govTz = [TimeZoneInfo]::FindSystemTimeZoneById('W. Europe Standard Time')
    function At([string]$u) { return (Get-Stamp -UtcAt ([DateTime]::SpecifyKind([DateTime]::Parse($u, [Globalization.CultureInfo]::InvariantCulture), [DateTimeKind]::Utc))) }
    $cases = @(
        @('2026-10-24 23:59:00', '2026-10-25 01:59:00 +02:00'),
        @('2026-10-25 00:30:00', '2026-10-25 02:30:00 +02:00'),   # first pass of the ambiguous hour
        @('2026-10-25 01:30:00', '2026-10-25 02:30:00 +01:00'),   # second pass
        @('2026-10-25 02:00:00', '2026-10-25 03:00:00 +01:00'),
        @('2026-03-29 00:59:00', '2026-03-29 01:59:00 +01:00'),
        @('2026-03-29 01:01:00', '2026-03-29 03:01:00 +02:00'),
        @('2026-07-04 10:00:00', '2026-07-04 12:00:00 +02:00'),
        @('2026-12-25 11:00:00', '2026-12-25 12:00:00 +01:00'))
    foreach ($c in $cases) { $got = At $c[0]; Assert ($got -eq $c[1]) "zone label at $($c[0])Z: expected $($c[1]), got $got" }
} else { Write-Output 'SKIP  engine has no -UtcAt stamp parameter; case 14 not run' }

# 16 AI-extension-host exemption, checked against an independent parent query
if ($engineText -match 'claudehost') {
    $claudeParents = @(Get-CimInstance Win32_Process -Filter "Name='claude.exe' OR Name='codex.exe'" | ForEach-Object { [int]$_.ParentProcessId } | Sort-Object -Unique)
    $exemptIndep = @($nodePids | Where-Object { $claudeParents -contains $_ } | Sort-Object)
    Write-Cfg 2 @('claude', 'Code') @('explorer', 'dwm')
    $r = Run-Engine @('-ListCode')
    $rowsL = @($r.out -split "`n" | Where-Object { $_ -match '^\s+\d+\s+\d{4}-\d\d-\d\d' })
    $flagged = @($rowsL | Where-Object { $_ -match 'claudehost\s*$' } | ForEach-Object { [int](($_.Trim() -split '\s+')[0]) } | Sort-Object)
    $unflagged = @($rowsL | Where-Object { $_ -notmatch 'claudehost\s*$' } | ForEach-Object { [int](($_.Trim() -split '\s+')[0]) })
    if ($exemptIndep.Count -eq 0) { Write-Output 'NOTE  no Code NodeService host parents a live claude.exe or codex.exe right now; case 16 is vacuous on this run' }
    Assert (($flagged -join ',') -eq ($exemptIndep -join ',')) "-ListCode marks exactly the independent parent-query hosts: marked [$($flagged -join ',')], independent [$($exemptIndep -join ',')]"
    $stillEligible = @($unflagged | Where-Object { $exemptIndep -notcontains $_ -and $nodePids -contains $_ })
    Assert ($stillEligible.Count -eq $unflagged.Count) "hosts that parent no claude.exe stay eligible ($($unflagged.Count) listed, none of them an AI-extension host)"
    # prime a quiet history (30 s needed with code_idle_runs 1 and a 1 minute cadence) so Code hosts can really be candidates in the run that follows
    Write-Cfg 2 @('claude', 'Code') @('explorer', 'dwm') @{ code_idle_runs = 1; cadence_minutes = 1 }
    Remove-Item (Join-Path $tmp 'govern.state.json') -Force -ErrorAction SilentlyContinue
    [void](Run-Engine @('-Mode', 'task'))
    Start-Sleep -Seconds 36
    $r = Run-Engine @('-Mode', 'task', '-List')
    $lastL = (Get-Content $logPath | Select-Object -Last 1)
    Assert ($lastL -match ' stage2 task DRY' -and $lastL -match ' claudehost (\d+)') "the stage 2 dry line carries 'claudehost N': $(([regex]::Match($lastL, ' claudehost \d+')).Value)"
    $nSkip = [int]([regex]::Match($lastL, ' claudehost (\d+)')).Groups[1].Value
    Assert ($nSkip -eq $exemptIndep.Count) "the dry line counts every exempt host (claudehost $nSkip, independent $($exemptIndep.Count))"
    $candRows = @($r.out -split "`n" | Where-Object { $_ -match '^\s+\d+\s+\d{4}-.*Code ' } | ForEach-Object { [int](($_.Trim() -split '\s+')[0]) })
    $leakC = @($candRows | Where-Object { $exemptIndep -contains $_ })
    Assert ($leakC.Count -eq 0) "no exempt host appears among the $($candRows.Count) Code candidate rows of -Mode task -List ($($leakC.Count) leaked)"
    if ($candRows.Count -eq 0) { Write-Output 'NOTE  no Code host was a candidate in the primed run, so the leak check above is vacuous on this run' }
    else { Assert ($candRows.Count -ge 1) "the primed run had Code candidates ($($candRows.Count)), so the leak check is not vacuous" }
} else { Write-Output 'SKIP  engine has no claude-host exemption; case 16 not run' }

# 15 the run lock. The self-check itself holds the engine's (self-check) lock, so the engine runs below meet a busy lock.
if ($engineText -match 'task_lock_wait_seconds' -and $hasMutexParam) {
    $mx = New-Object System.Threading.Mutex($false, 'Local\RamGovernSelfcheck')
    $held = $mx.WaitOne(0)
    Assert $held 'lock case setup: the self-check holds the engine run lock'
    try {
        Write-Cfg 1 @('claude') @('Code', 'explorer', 'dwm') @{ task_lock_wait_seconds = 2 }
        $before = Line-Count
        $r = Run-Engine @('-Mode', 'task')
        $new = @(Get-Content $logPath | Select-Object -Skip $before)
        Assert ($r.code -eq 4) "task run, lock held, 2 s wait: exit 4 (got $($r.code))"
        $okSkip = ($new.Count -eq 1 -and $new[0] -match ' task SKIP: run lock held, waited (\d+) ms$' -and [int]$Matches[1] -ge 1900)
        Assert $okSkip "task run logs one SKIP line after waiting at least 1900 ms: $($new -join ' | ')"

        $before = Line-Count
        $r = Run-Engine @('-Mode', 'self', '-TargetPid', "$PID")
        $new = @(Get-Content $logPath | Select-Object -Skip $before)
        Assert ($r.code -eq 4 -and $new.Count -eq 1 -and $new[0] -match ' self SKIP: run lock held, waited \d+ ms$') "self run, lock held: exit 4 and one SKIP line: $($new -join ' | ')"

        Write-Cfg 1 @('claude') @('Code', 'explorer', 'dwm') @{ task_lock_wait_seconds = 0 }
        $before = Line-Count
        $r = Run-Engine @('-Mode', 'task')
        $new = @(Get-Content $logPath | Select-Object -Skip $before)
        $okZero = ($r.code -eq 4 -and $new.Count -eq 1 -and $new[0] -match ' task SKIP: run lock held, waited (\d+) ms$' -and [int]$Matches[1] -lt 500)
        Assert $okZero "wait 0: the task does not wait: $($new -join ' | ')"

        Write-Cfg 1 @('claude') @('Code', 'explorer', 'dwm') @{ task_lock_wait_seconds = 60 }
        $before = Line-Count
        $proc = Start-Process -FilePath 'powershell.exe' -PassThru -WindowStyle Hidden -ArgumentList @('-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', $Engine, '-Config', $cfgPath, '-MutexName', 'Local\RamGovernSelfcheck', '-Mode', 'task')
        [void]$proc.Handle
        Start-Sleep -Seconds 7
        $mx.ReleaseMutex(); $held = $false
        [void]$proc.WaitForExit(240000)
        $new = @(Get-Content $logPath | Select-Object -Skip $before)
        Assert ($proc.ExitCode -eq 0) "lock released mid-wait: the task run goes on and exits 0 (got $($proc.ExitCode))"
        $okWait = ($new.Count -eq 2 -and $new[0] -match ' task START: .*lock-wait (\d+) ms$' -and [int]$Matches[1] -ge 1000 -and $new[1] -match ' task DRY: ')
        Assert $okWait "START line shows the wait (lock-wait 1000 ms or more) and a DRY line follows: $($new[0])"
    } finally {
        if ($held) { try { $mx.ReleaseMutex() } catch { } }
        $mx.Dispose()
    }
} else { Write-Output 'SKIP  engine has no task_lock_wait_seconds; case 15 not run' }

Remove-Item -Recurse -Force $tmp
if ($fails -eq 0) { Write-Output 'govern_selfcheck: ALL PASSED'; exit 0 } else { Write-Output "govern_selfcheck: $fails FAILED"; exit 1 }
