@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -m facturas_excel.app
if errorlevel 1 pause
