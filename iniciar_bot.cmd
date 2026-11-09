@echo off
rem Arranca el bot y lo relanza si se cae. El log queda en logs\bot.log.
rem Uso: doble clic, o desde el Programador de tareas al iniciar sesion.
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
if not exist logs mkdir logs
:loop
echo [%date% %time%] iniciando bot >> logs\bot.log
.venv\Scripts\python -m tradebot.run >> logs\bot.log 2>&1
echo [%date% %time%] el bot se detuvo; se relanza en 60 s >> logs\bot.log
timeout /t 60 /nobreak >nul
goto loop
