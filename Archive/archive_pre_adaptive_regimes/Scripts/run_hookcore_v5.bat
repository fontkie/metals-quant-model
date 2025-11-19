@echo off
REM ========================================
REM HookCore v5 Build Script (Windows)
REM ========================================
REM
REM Expected Performance:
REM   Sharpe: 0.50-0.60 (symmetric)
REM   Activity: 12-15% (both directions)
REM   Vol: ~2-3%
REM
REM ========================================

echo.
echo ========================================
echo Building HookCore v5 (Copper)
echo ========================================
echo.

python src\cli\build_hookcore_v5.py ^
    --csv-price Data\copper\pricing\canonical\copper_lme_3mo.canonical.csv ^
    --config Config\Copper\hookcore_v5.yaml ^
    --outdir outputs\Copper\HookCore_v5

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
echo Results saved to: outputs\Copper\HookCore_v5
echo.
echo Next steps:
echo   1. Review daily_series.csv for full backtest
echo   2. Check summary_metrics.json for performance
echo   3. Run regime analysis if needed
echo.

pause