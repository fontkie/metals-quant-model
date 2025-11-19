@echo off
REM =================================================================
REM Run Static Portfolio - Proper Portfolio-Level Costs
REM 
REM Location: C:\Code\Metals\scripts\run_vol_static.bat
REM Calls: C:\Code\Metals\toolssrc\cli\build_static_portfolio.py
REM Input: outputs\Copper\VolRegime\vol_static_weights.csv
REM Output: outputs\Copper\VolStatic\
REM =================================================================

echo.
echo ===================================================================
echo VOL STATIC PORTFOLIO - Static Weight Baseline
echo ===================================================================
echo.
echo Applies static weights throughout entire period (no regime awareness)
echo.
echo Weights from: outputs\Copper\VolRegime\vol_static_weights.csv
echo Output to:    outputs\Copper\VolStatic\
echo.

REM Change to project root
cd /d "%~dp0.."

REM Run the Python script
python src\cli\build_vol_static_portfolio.py ^
    --config "Config\Copper\vol_static_portfolio.yaml" ^
    --weights "outputs\Copper\VolRegime\vol_static_weights.csv" ^
    --outdir "outputs\Copper\VolStatic"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Static portfolio build failed!
    pause
    exit /b 1
)

echo.
echo ===================================================================
echo Static portfolio built!
echo Check: outputs\Copper\VolStatic\
echo.
echo Compare with adaptive portfolio for regime-awareness benefit
echo ===================================================================
echo.

pause