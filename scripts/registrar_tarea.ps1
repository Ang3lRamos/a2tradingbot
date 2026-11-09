# Registra el bot en el Programador de tareas para que arranque al iniciar sesion,
# con la misma configuracion que los bots mt5bot: 1 minuto de espera, sin limite de tiempo,
# tambien con bateria. Luego lo arranca de inmediato.
#
# Uso:    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\registrar_tarea.ps1
# Quitar: Unregister-ScheduledTask -TaskName tradebot -Confirm:$false

$ErrorActionPreference = "Stop"
$launcher = Join-Path (Split-Path $PSScriptRoot -Parent) "iniciar_bot.cmd"

$running = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "tradebot\.run" }
if ($running) {
    Write-Host "Ya hay un bot corriendo (PID $($running.ProcessId -join ', ')). Detenlo antes para no tener dos copias." -ForegroundColor Yellow
    exit 1
}

$action = New-ScheduledTaskAction -Execute $launcher -WorkingDirectory (Split-Path $launcher -Parent)
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$trigger.Delay = "PT1M"
# ExecutionTimeLimit 0 = sin limite. Por defecto Windows detiene las tareas a las 72 horas.
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit 0 -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName "tradebot" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null

Start-ScheduledTask -TaskName "tradebot"
Write-Host "Tarea 'tradebot' registrada y en marcha. Log: logs\bot.log" -ForegroundColor Green
