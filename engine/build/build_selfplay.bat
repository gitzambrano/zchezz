@echo off
REM Native selfplay.c uses the NNU4 per-instance NnueNet API.
REM Keep its tool host on v506. For v3.28/NNU3 self-play use:
REM   python tests\run_selfplay.py --engine-path engine\c\zchezz_v328\zchezz.exe
set TOOLS_ENGINE=v506
if not "%~1"=="" set TOOLS_ENGINE=%~1
set "PATH=C:\mingw64\bin;%PATH%"
cd /d "%~dp0"
echo Compiling native NNU4 selfplay tool (TOOLS_ENGINE=%TOOLS_ENGINE%)...
mingw32-make.exe TOOLS_ENGINE=%TOOLS_ENGINE% selfplay
if %ERRORLEVEL% equ 0 (
    echo.
    echo SUCCESS: Compilation complete! -^> selfplay.exe
    echo NOTE: v3.28 self-play uses tests\run_selfplay.py through UCI.
    echo.
) else (
    echo.
    echo ERROR: Compilation failed.
    echo.
)
pause
