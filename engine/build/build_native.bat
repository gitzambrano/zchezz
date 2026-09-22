@echo off
REM Shared native build launcher. Bare execution builds the active engine (v330).
REM Pass v506 (or another explicit retained source version) as the first argument to override.
set "ENGINE=%~1"
if not defined ENGINE set /p ENGINE=<"%~dp0..\ACTIVE_ENGINE"
if not defined ENGINE set ENGINE=v330
set "PATH=C:\mingw64\bin;%PATH%"
cd /d "%~dp0"
echo Compiling Zchezz (ENGINE=%ENGINE%)...
mingw32-make.exe ENGINE=%ENGINE% native
if %ERRORLEVEL% equ 0 (
    echo.
    echo SUCCESS: Compilation complete!
    echo.
) else (
    echo.
    echo ERROR: Compilation failed.
    echo.
)
pause
