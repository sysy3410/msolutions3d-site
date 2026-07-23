@echo off
REM ============================================================
REM  MSolution - Definir le mot de passe administrateur
REM ============================================================
cd /d "%~dp0backend"
"venv\Scripts\python.exe" set_password.py
echo.
pause
