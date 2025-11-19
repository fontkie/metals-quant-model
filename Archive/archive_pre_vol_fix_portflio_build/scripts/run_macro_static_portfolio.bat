@echo off
REM =================================================================
REM Build Macro Static Portfolio - Baseline Performance
REM Applies vol_static_weights across all days, measures by macro state
REM 
REM Location: C:\Code\Metals\scripts\run_macro_static_portfolio.bat
REM Calls: C:\Code\Metals\tools\build_macro_static_portfolio.py
REM Output: C:\Code\Metals\outputs\Copper\MacroStatic\macro_static_portfolio_performance.csv
REM =================================================================

echo.
echo ===================================================================
echo MACRO STATIC PORTFOLIO - BASELINE PERFORMANCE
echo ===================================================================
echo.
echo This applies vol_static_weights (40/15/45) to all days and measures
echo performance by macro state (NORMAL/CHOP/CRISIS).
echo.
echo This is the BASELINE before Path B adjustments.
echo.

REM Change to project root
cd /d "%~dp0.."

REM Run the Python script
python tools\build_macro_static_portfolio.py ^
    --vol-weights "outputs\Copper\VolRegime\vol_static_weights.csv" ^
    --macro-regimes "outputs\Copper\MacroRegime\macro_regimes.csv" ^
    --sleeve-dir "outputs\Copper" ^
    --outdir "outputs\Copper\MacroStatic" ^
    --start-date 2000-01-01 ^
    --end-date 2025-12-31

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Macro static portfolio calculation failed!
    pause
    exit /b 1
)

echo.
echo ===================================================================
echo Baseline performance saved!
echo Check: outputs\Copper\MacroStatic\macro_static_portfolio_performance.csv
echo.
echo Next: Run Path B optimizer to find CHOP/CRISIS multipliers
echo ===================================================================
echo.

pause