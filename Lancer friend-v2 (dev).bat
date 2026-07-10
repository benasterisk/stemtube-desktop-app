@echo off
REM ============================================================================
REM  Lance le backend Flask de stemtube-desktop-friend-v2 pour le developpement.
REM
REM  - Utilise le venv de l'ancien dossier "stemtube-desktop-friend" (friend-v2
REM    n'a pas son propre venv : il a ete exclu de la copie, 5.2 Go).
REM  - Pointe STEMTUBE_DATA_DIR sur tes vraies donnees (bibliotheque + DB de
REM    prod de StemTube Desktop Friend) pour que tu retrouves tes morceaux.
REM    NOTE: c'est la MEME base que l'app habituelle -> evite de lancer les deux
REM    en meme temps, et reste prudent (lecture pour tester, ok ; les extractions
REM    ecrivent dans cette base).
REM
REM  Lance launcher.py -> ouvre une FENETRE DESKTOP native (pywebview / WebView2),
REM  exactement comme l'app StemTube habituelle. Pas besoin de navigateur.
REM  (Toute la coquille StemTube y est : My Library, Download, sidebar ; le mixer
REM  s'ouvre DANS la fenetre quand tu cliques "Open Mixer" sur un morceau.)
REM ============================================================================

setlocal
set "V2=%~dp0"
set "FRIEND=%V2%..\stemtube-desktop-friend"
set "PYEXE=%FRIEND%\venv\Scripts\python.exe"

REM Pointe sur les vraies donnees de StemTube Desktop Friend.
set "STEMTUBE_DATA_DIR=%LOCALAPPDATA%\StemTube Desktop Friend"

if not exist "%PYEXE%" (
  echo [ERREUR] Python du venv introuvable : "%PYEXE%"
  echo Le venv doit exister dans le dossier stemtube-desktop-friend.
  pause
  exit /b 1
)

echo ============================================================
echo  StemTube friend-v2 (DEV) - fenetre desktop
echo  Python    : %PYEXE%
echo  Data dir  : %STEMTUBE_DATA_DIR%
echo  (Une fenetre StemTube Desktop va s'ouvrir. Fermer la fenetre
echo   arrete le serveur.)
echo ============================================================
echo.

cd /d "%V2%"
"%PYEXE%" launcher.py

echo.
echo [Serveur arrete]
pause
endlocal
