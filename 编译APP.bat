set "SCRIPT_DIR=%~dp0"
python -O -m PyInstaller -y -F  -n APP  %SCRIPT_DIR%\app.py  
@pause
@pause