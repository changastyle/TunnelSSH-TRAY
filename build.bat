@echo off
REM Compila la app a un .exe unico (dist\ClinicTunnel.exe)
pip install -r requirements.txt pyinstaller
pyinstaller --noconsole --onefile --name ClinicTunnel --add-data "UTILS;UTILS" tray_tunnel.py
copy tunnel_key dist\
echo.
echo Listo: dist\ClinicTunnel.exe (tunnel_key copiado junto al exe, es necesario)
pause
