@echo off
REM ========================================
REM Build Copper Demand Overlay - YoY Method
REM ========================================
REM
REM This script applies the YoY (12-month momentum) copper demand overlay.
REM
REM CONFIGURATION: YoY with 2-month publication lag
REM EXPECTED RESULTS: +0.064 Sharpe improvement, -20.02% max DD
REM
REM NOTE: YoY is inferior to QoQ based on lag sensitivity analysis.
REM       Use this for comparison only.
REM
REM Author: Kieran
REM Date: November 20, 2025

echo ================================================================================
echo Building Copper Demand Overlay - YoY (12-Month Momentum)
echo ================================================================================
echo.

REM Set paths
set BASELINE=C:\Code\Metals\outputs\Copper\Portfolio\BaselineEqualWeight\latest\daily_series.csv
set CONFIG=Config\copper\copper_demand.yaml

REM YoY configuration
set METHOD=--method yoy
set LAG=--lag 2

echo Baseline:  %BASELINE%
echo Config:    %CONFIG%
echo Method:    YoY (12-month momentum)
echo Lag:       2 months
echo.

cd /d C:\Code\Metals

REM Run build script
python src\cli\build_copper_demand.py ^
    --baseline "%BASELINE%" ^
    --config %CONFIG% ^
    %METHOD% ^
    %LAG%

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
echo BUILD COMPLETE - YoY METHOD
echo ================================================================================
echo.
echo Expected Results:
echo   Sharpe improvement: ~+0.064 (+7.0%%)
echo   Max drawdown: ~-20.02%% (worse than baseline)
echo.
echo Output location: outputs\Copper\Portfolio\copper_demand\lag_2\
echo Files: Look for *yoy_2mo*.csv and *yoy_2mo*.txt
echo.
echo NOTE: QoQ method performs better (+0.096 vs +0.064 Sharpe)
echo       Compare summary_qoq_2mo_*.txt vs summary_yoy_2mo_*.txt
echo.
echo Next steps:
echo   1. Review summary_yoy_2mo_*.txt for performance metrics
echo   2. Compare to QoQ results (already generated)
echo   3. Deploy QoQ as primary method (better performance)
echo.

pause
exit /b 0