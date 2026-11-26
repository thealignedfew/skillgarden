# register_brake.ps1  registers the ramgovern brake and the sampler as scheduled tasks for the current user (0.2.0).
# Run it once, by hand, from this folder. Look first:
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\register_brake.ps1 -DryRun
# then register:
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\register_brake.ps1
#
# Two tasks, each started at your logon and kept to one copy:
#   ramgovern-brake    runs brake.ps1: slows the targets in brake.json while you are at the machine. It ships with no
#                      targets, so until you add one it only writes the once-a-minute memory and drive lines.
#   ramgovern-sampler  runs sampler.ps1: one read-only line every 15 seconds for the suggester.
# Both run as you (interactive logon, limited rights, no elevation), hidden through conhost --headless so no console window
# flashes, and neither is stopped on battery. The scripts keep their own one-copy lock, so a second start exits at once.
# Add -NoSampler to register only the brake.
#
# Where files go: the ramgovern home (RAMGOVERN_HOME, else the folder holding govern.json, else .threadops\ramgovern in your
# profile). The tasks are told that folder, so they keep working if the variable is not set at logon.
# Undo:
#   Unregister-ScheduledTask -TaskName ramgovern-brake -Confirm:$false
#   Unregister-ScheduledTask -TaskName ramgovern-sampler -Confirm:$false
# then stop the two powershell processes whose command line names brake.ps1 or sampler.ps1 (look them up in Task Manager).
param(
    [switch]$DryRun,
    [switch]$NoSampler
)
$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$home1 = $env:RAMGOVERN_HOME
if (-not $home1) {
    foreach ($d in @($here, (Split-Path $here -Parent))) { if ($d -and (Test-Path (Join-Path $d 'govern.json'))) { $home1 = $d; break } }
}
if (-not $home1) { $home1 = Join-Path $env:USERPROFILE '.threadops\ramgovern' }
$jobs = @(@{ Name = 'ramgovern-brake'; Script = 'brake.ps1'; Args = "-Config `"$(Join-Path $home1 'brake.json')`" -Log `"$(Join-Path $home1 'govern.log')`"" })
if (-not $NoSampler) { $jobs += @{ Name = 'ramgovern-sampler'; Script = 'sampler.ps1'; Args = "-OutDir `"$home1`"" } }
foreach ($j in $jobs) {
    $script = Join-Path $here $j.Script
    if (-not (Test-Path $script)) { throw "$($j.Script) not found beside this script ($script)" }
    $arg = "--headless powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$script`" $($j.Args)"
    if ($DryRun) {
        Write-Output "WOULD register $($j.Name): conhost.exe $arg"
        continue
    }
    if (Get-ScheduledTask -TaskName $j.Name -ErrorAction SilentlyContinue) { Write-Output "$($j.Name) already registered; nothing changed"; continue }
    if (-not (Test-Path $home1)) { New-Item -ItemType Directory -Path $home1 -Force | Out-Null }
    $action = New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\conhost.exe" -Argument $arg
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
    $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero)
    Register-ScheduledTask -TaskName $j.Name -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "ramgovern: $($j.Script), started at logon" | Out-Null
    Write-Output "registered $($j.Name): runs at your next logon. To start it now: Start-ScheduledTask -TaskName $($j.Name)"
}
