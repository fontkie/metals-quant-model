@echo off
REM ============================================================================
REM Extract Vol Regimes from Adaptive Portfolio Output
REM ============================================================================
REM Location: C:\Code\Metals\scripts\run_extract_vol.bat
REM ============================================================================

echo.
echo ================================================================================
echo EXTRACTING VOL REGIMES
echo ================================================================================
echo.

REM Set paths (lowercase to match your structure)
set TOOLS_DIR=..\tools
set OUTPUT_DIR=..\outputs\RegimeData

REM Input file (note: includes \Copper subfolder)
set INPUT_FILE=..\outputs\Copper\AdaptivePortfolio\regime_log.csv

REM Output file
set OUTPUT_FILE=%OUTPUT_DIR%\vol_regimes.csv

REM Create output directory if it doesn't exist
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"

REM Check input exists
if not exist "%INPUT_FILE%" (
    echo ❌ ERROR: Input file not found
    echo Expected location: %INPUT_FILE%
    echo.
    echo Please check:
    echo 1. Adaptive portfolio has been run
    echo 2. regime_log.csv exists in outputs\Copper\AdaptivePortfolio\
    pause
    exit /b 1
)

REM Run extraction
python %TOOLS_DIR%\extract_vol_regimes.py %INPUT_FILE% %OUTPUT_FILE%

if %errorlevel% neq 0 (
    echo.
    echo ❌ ERROR: Vol regime extraction failed!
    pause
    exit /b 1
)

echo.
echo ================================================================================
echo ✓ SUCCESS!
echo Vol regimes saved to: %OUTPUT_FILE%
echo ================================================================================
echo.
pause