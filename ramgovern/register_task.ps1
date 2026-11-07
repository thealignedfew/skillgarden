# register_task.ps1  registers the ramgovern scheduled task for the current user. Run it once, by hand, from this folder:
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\register_task.ps1
#
# The task runs govern.ps1 -Mode task -Apply every 5 minutes as the current user (interactive logon, limited rights, no
# elevation), on battery too, one instance at a time, with a 10 minute hang guard (a run takes about 70 seconds).
#   - conhost.exe --headless hosts PowerShell so no console window flashes and steals focus every 5 minutes. Side effect: the
#     task's Last Result reads 0 whatever the engine's exit code, so read govern.log, not the scheduler, to see what happened.
#   - a time trigger repeating with no end starts at once and keeps going across logons and reboots (a logon trigger with
#     repetition would not begin until the next logon).
# Nothing is trimmed until govern.json has "enabled": true; until then every run writes a DRY line.
# Undo: Unregister-ScheduledTask -TaskName ramgovern -Confirm:$false
param(
    [string]$TaskName = 'ramgovern',
    [int]$CadenceMinutes = 5
)
$ErrorActionPreference = 'Stop'
$engine = Join-Path $PSScriptRoot 'govern.ps1'
if (-not (Test-Path $engine)) { throw "govern.ps1 not found beside this script ($engine)" }
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) { Write-Output "$TaskName already registered; nothing changed"; exit 0 }
$start = (Get-Date).AddMinutes(1); $start = $start.AddSeconds(-$start.Second)
$action = New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\conhost.exe" -Argument "--headless powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$engine`" -Mode task -Apply"
$trigger = New-ScheduledTaskTrigger -Once -At $start -RepetitionInterval (New-TimeSpan -Minutes $CadenceMinutes)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'ramgovern: pages idle Claude Code sessions and idle VS Code extension hosts out of RAM. Settings in govern.json beside govern.ps1 (enabled false stops trimming); halts itself on a page-in storm (govern.stop).' | Out-Null
$t = Get-ScheduledTask -TaskName $TaskName
Write-Output ("registered {0}: state={1} runlevel={2} logon={3} first run {4:HH:mm} then every {5}" -f $TaskName, $t.State, $t.Principal.RunLevel, $t.Principal.LogonType, $start, $t.Triggers[0].Repetition.Interval)
if ($CadenceMinutes -ne 5) { Write-Output "set cadence_minutes to $CadenceMinutes in govern.json too, or every run logs a MISMATCH note" }
if ($TaskName -ne 'ramgovern') { Write-Output "set task_name to $TaskName in govern.json too, or the cadence check cannot find the task" }
