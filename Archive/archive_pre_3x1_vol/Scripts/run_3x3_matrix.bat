@echo off
REM ============================================================================
REM 3×3 Performance Matrix Calculator - Runner
REM ============================================================================
REM 
REM Combines Vol + Trend regimes and analyzes sleeve performance.
REM Calculates on IN-SAMPLE period (2000-2018) to avoid forward bias.
REM 
REM Inputs:  outputs\Copper\VolRegime\vol_regimes.csv
REM          outputs\Copper\VolRegime\adx_trend_regimes.csv
REM          outputs\Copper\[TrendMedium|TrendImpulse_v4|MomentumCore_v1]\daily_series.csv
REM Code:    C:\Code\Metals\tools\build_3x3_matrix.py
REM Outputs: outputs\Copper\VolRegime\sleeve_performance_3x3_matrix.csv
REM          outputs\Copper\VolRegime\regime_classification_vol_trend.csv
REM
REM Author: Ex-Renaissance Quant
REM Date: November 12, 2025
REM ============================================================================

cd /d %~dp0\..
set PYTHONPATH=%CD%

echo.
echo ========================================
echo 3x3 Performance Matrix Calculator
echo ========================================
echo.

python tools\build_3x3_matrix.py

if %errorlevel% neq 0 (
    echo.
    echo ❌ Matrix calculation failed!
    pause
    exit /b 1
)

echo.
echo ✅ Matrix calculation complete!
echo.
echo Outputs saved to:
echo   outputs\Copper\VolRegime\sleeve_performance_3x3_matrix.csv
echo   outputs\Copper\VolRegime\regime_classification_vol_trend.csv
echo.
pause