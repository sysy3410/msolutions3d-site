@echo off
REM ============================================================
REM  MSolution - Demarrage du serveur du site
REM ============================================================
cd /d "%~dp0backend"
echo ============================================================
echo   Site MSolution
echo   Site    : http://127.0.0.1:8123/
echo   Admin   : http://127.0.0.1:8123/admin.html
echo.
echo   IMPORTANT : consultez le site via CETTE adresse dans le
echo   navigateur. N'ouvrez PAS les fichiers .html en double-clic
echo   (les realisations et l'admin ne fonctionneraient pas).
echo.
echo   Fermez cette fenetre pour arreter le serveur.
echo ============================================================
echo.

REM Ouvre le navigateur automatiquement apres 2 secondes,
REM le temps que le serveur demarre.
start "" cmd /c "timeout /t 2 /nobreak >nul & start "" http://127.0.0.1:8123/"

"venv\Scripts\python.exe" run.py
pause
