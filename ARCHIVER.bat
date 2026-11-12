@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Archive jeuxvideo.rds.ca (Wayback Machine)
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo.
echo  ==============================================================
echo   Archive de jeuxvideo.rds.ca depuis la Wayback Machine
echo  --------------------------------------------------------------
echo   Tu peux fermer cette fenetre ou eteindre l'ordinateur quand
echo   tu veux : la prochaine fois, ca reprend la ou ca s'est arrete.
echo   Pour arreter proprement : Ctrl+C (puis O ou Y).
echo  ==============================================================
echo.

where git >nul 2>nul
if errorlevel 1 (
  echo [!] Git n'est pas installe. Installe-le depuis https://git-scm.com/download/win
  pause & exit /b 1
)
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY (
  echo [!] Python n'est pas installe. Installe-le depuis https://www.python.org/downloads/
  echo     ^(coche "Add python.exe to PATH" pendant l'installation^)
  pause & exit /b 1
)

rem --- reglages Git pour ce dossier seulement ---
git config core.longpaths true
git config core.autocrlf false
git config user.name >nul 2>nul || git config user.name "Mario J. Ramos"
git config user.email >nul 2>nul || git config user.email "mjramos86@users.noreply.github.com"

echo Mise a jour depuis GitHub...
git pull -q --rebase origin main
if errorlevel 1 (
  echo [!] Impossible de recuperer la derniere version. Verifie ta connexion Internet.
  pause & exit /b 1
)

:loop
%PY% scripts\wayback_dump.py fetch
if %errorlevel%==0 goto done
echo.
echo Pause de 5 minutes avant de reprendre (Ctrl+C pour arreter)...
timeout /t 300 /nobreak >nul
git pull -q --rebase origin main
goto loop

:done
echo.
echo  Termine! Tout ce que la Wayback Machine avait est dans le depot.
pause
