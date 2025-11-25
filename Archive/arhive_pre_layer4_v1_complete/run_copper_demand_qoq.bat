@echo off
REM ========================================
REM Build Copper Demand Overlay (Copper)
REM ========================================
REM
REM This script applies the Copper demand overlay to a baseline portfolio.
REM
REM UPDATED: November 20, 2025
REM - Fixed baseline path to use BaselineEqualWeight output
REM - Added support for YoY vs QoQ comparison
REM - Fixed argument parsing
REM
REM Author: Kieran

echo ================================================================================
echo Building Copper Demand Overlay (Copper)
echo ================================================================================
echo.

REM Set paths
set BASELINE=C:\Code\Metals\outputs\Copper\Portfolio\BaselineEqualWeight\latest\daily_series.csv
set CONFIG=Config\copper\copper_demand.yaml

REM Optional: Override lag setting (uncomment to use)
REM set LAG_OVERRIDE=--lag 1

REM Optional: Choose method (yoy or qoq)
REM Default is qoq if not specified in config
REM set METHOD=--method qoq

echo Baseline:  %BASELINE%
echo Config:    %CONFIG%
echo.

cd /d C:\Code\Metals

REM Run build script
python src\cli\build_copper_demand.py ^
    --baseline "%BASELINE%" ^
    --config %CONFIG% ^
    %LAG_OVERRIDE% ^
    %METHOD%

if %errorlevel% neq 0 (
    echo.
    echo ================================================================================
    echo BUILD FAILED
    echo ================================================================================
    echo Review the error messages above
    echo.
    pause
    exit /b 1
)

echo.
echo ================================================================================
echo BUILD COMPLETE
echo ================================================================================
echo.
echo Next steps:
echo   1. Review summary_*.txt for performance metrics
echo   2. Validate NEUTRAL regime matching
echo   3. Compare YoY vs QoQ results if needed
echo   4. Deploy best-performing method
echo.

pause
exit /b 0