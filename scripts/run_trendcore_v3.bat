@echo off
REM ========================================
REM TrendCore v3 Build Script (Windows)
REM ========================================
REM
REM Expected Performance:
REM   Sharpe: 0.51 (unconditional)
REM   Sharpe: 2.0-2.5 (in trending regimes)
REM   Max DD: -13.7%
REM   Annual Vol: ~4.6%
REM
REM ========================================

echo.
echo ========================================
echo Building TrendCore v3 (Copper)
echo ========================================
echo.

python src\cli\build_trendcore_v3.py ^
    --csv Data\copper\pricing\canonical\copper_lme_3mo.canonical.csv ^
    --config Config\Copper\trendcore.yaml ^
    --outdir outputs\Copper\TrendCore_v3

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
echo Results saved to: outputs\Copper\TrendCore_v3
echo.
echo Next steps:
echo   1. Review daily_series.csv for full backtest
echo   2. Check summary_metrics.json for performance
echo   3. Run regime analysis if needed
echo.

pause