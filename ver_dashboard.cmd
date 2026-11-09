@echo off
rem Abre el dashboard (Next.js) en http://localhost:3000. Cerrar esta ventana lo detiene.
rem La primera vez instala dependencias y compila; despues arranca directo.
cd /d "%~dp0web"
if not exist node_modules call npm install
if not exist .next\BUILD_ID call npm run build
start "" http://localhost:3000
call npm run start
