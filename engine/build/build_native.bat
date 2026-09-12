@echo off
REM Shared native build launcher. Bare execution builds the repository default v326.
REM Pass v500 (or another explicit retained source version) as the first argument to override.
set ENGINE=v326
if not "%~1"=="" set ENGINE=%~1
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
