@echo off
REM ========================================
REM TrendMedium Build Script (Windows)
REM ========================================
REM
REM Expected Performance:
REM   Sharpe: 0.45-0.55 (unconditional)
REM   Faster response than TrendCore
REM   Targets 2-4 month trends
REM
REM ========================================

echo.
echo ========================================
echo Building TrendMedium (Copper)
echo ========================================
echo.

python src\cli\build_trendmedium.py ^
    --csv Data\copper\pricing\canonical\copper_lme_3mo.canonical.csv ^
    --config Config\Copper\trendmedium.yaml ^
    --outdir outputs\Copper\TrendMedium

if %errorlevel% neq 0 (
    echo.
    echo ========================================
    echo Build FAILED!
    echo ========================================
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo Build COMPLETE!
echo ========================================
echo.
echo Results saved to: outputs\Copper\TrendMedium
echo.
echo Next steps:
echo   1. Review daily_series.csv for full backtest
echo   2. Check summary_metrics.json for performance
echo   3. Compare with TrendCore v3 (30/100 MAs)
echo   4. Run regime analysis if needed
echo.

pause