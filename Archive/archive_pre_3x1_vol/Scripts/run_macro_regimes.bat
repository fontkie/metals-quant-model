@echo off
REM ============================================================================
REM Macro Regime Classifier - Runner
REM ============================================================================
REM 
REM Combines ChopCore and CrisisCore into 3 macro states: NORMAL/CHOP/CRISIS
REM (Does NOT combine with vol - that happens in macro_static_portfolio.py)
REM 
REM Inputs:  C:\Code\Metals\outputs\Copper\ChopCore_v1\chopcore_v1_regimes.csv
REM          C:\Code\Metals\outputs\Copper\CrisisCore_v2\crisiscore_v2_regimes.csv
REM Code:    C:\Code\Metals\tools\build_macro_regimes.py
REM Outputs: C:\Code\Metals\outputs\Copper\MacroRegime\macro_regimes.csv
REM
REM Author: Ex-Renaissance Quant + Kieran
REM Date: November 13, 2025
REM ============================================================================

cd /d %~dp0\..
set PYTHONPATH=%CD%

echo.
echo ========================================
echo Macro Regime Classifier
echo ========================================
echo.

python tools\build_macro_regimes.py

if %errorlevel% neq 0 (
    echo.
    echo ❌ Macro regime classification failed!
    pause
    exit /b 1
)

echo.
echo ✅ Macro regime classification complete!
echo.
echo Output saved to:
echo   outputs\Copper\MacroRegime\macro_regimes.csv
echo.
echo Next: Run build_macro_static_portfolio.py to combine with vol weights
echo.
pause