@echo off
REM ============================================================================
REM Volatility Regime Classifier - Runner
REM ============================================================================
REM 
REM Calculates realized volatility and classifies into LOW/MEDIUM/HIGH regimes.
REM 
REM Inputs:  C:\Code\Metals\Data\copper\pricing\canonical\copper_lme_3mo.canonical.csv
REM Code:    C:\Code\Metals\tools\build_vol_regimes.py
REM Outputs: C:\Code\Metals\outputs\Copper\VolRegime\vol_regimes.csv
REM
REM Author: Ex-Renaissance Quant
REM Date: November 12, 2025
REM ============================================================================

cd /d %~dp0\..
set PYTHONPATH=%CD%

echo.
echo ========================================
echo Volatility Regime Classifier
echo ========================================
echo.

python tools\build_vol_regimes.py

if %errorlevel% neq 0 (
    echo.
    echo ❌ Volatility classification failed!
    pause
    exit /b 1
)

echo.
echo ✅ Volatility classification complete!
echo.
echo Output saved to:
echo   outputs\Copper\VolRegime\vol_regimes.csv
echo.
pause