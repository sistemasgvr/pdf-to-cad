@echo off
REM Abre el administrador de la gestion del proyecto (local, en el navegador).
REM Este .bat vive en gestion\ : sube a la raiz del repo antes de correr.
cd /d "%~dp0.."
python scripts\gestion admin
pause
