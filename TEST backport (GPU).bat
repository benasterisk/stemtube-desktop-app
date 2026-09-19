@echo off
REM ============================================================================
REM  Lance CE dossier (D:\stemtube-desktop-app, branche port/r2-backport)
REM  dans une fenetre desktop, en GPU.
REM
REM  - Emprunte le venv de l'app Standard installee (torch cu124). Non modifie.
REM  - Donnees isolees dans C:\Users\benas\Documents\stemtube-test\data-standard
REM    => ta bibliotheque de production n'est pas touchee, la liste demarre VIDE.
REM
REM  ATTENTION : ce venv n'a PAS faster-whisper -> les paroles ne marcheront pas
REM  tant qu'il n'est pas installe (voir TEST-backport.md).
REM
REM  Pour revenir a l'etat d'avant :  git switch main
REM ============================================================================

setlocal
set "PYEXE=%LOCALAPPDATA%\StemTube Desktop\stemtube-backend-standard\venv\Scripts\python.exe"
set "STEMTUBE_DATA_DIR=%USERPROFILE%\Documents\stemtube-test\data-standard"

if not exist "%PYEXE%" (
  echo [ERREUR] Python introuvable : "%PYEXE%"
  pause
  exit /b 1
)
if not exist "%STEMTUBE_DATA_DIR%" mkdir "%STEMTUBE_DATA_DIR%"

for /f %%b in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set "BR=%%b"
echo ============================================================
echo  StemTube STANDARD - TEST   (branche : %BR%)
echo  Donnees : %STEMTUBE_DATA_DIR%   (isolees de la prod)
echo ============================================================
echo.

cd /d "%~dp0"
"%PYEXE%" launcher.py

echo.
echo [Serveur arrete]
pause
endlocal
