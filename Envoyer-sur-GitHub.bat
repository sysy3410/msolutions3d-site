@echo off
chcp 65001 >nul
cd /d "C:\Users\sylvain\Desktop\MSolution\Site internet"
echo ============================================================
echo   Envoi de la derniere version du site vers GitHub
echo ============================================================
echo.
echo La PREMIERE fois, une fenetre de connexion GitHub va s'ouvrir
echo dans votre navigateur : connectez-vous et cliquez "Authorize".
echo Les fois suivantes, ce sera automatique.
echo.
git push -u origin main
echo.
if %errorlevel%==0 (
  echo ------------------------------------------------------------
  echo   Envoi reussi ! Le code est sur GitHub.
  echo ------------------------------------------------------------
) else (
  echo ------------------------------------------------------------
  echo   Echec de l'envoi. Notez le message ci-dessus et
  echo   transmettez-le a Claude.
  echo ------------------------------------------------------------
)
echo.
pause
