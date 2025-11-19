@echo off
REM ========================================
REM TrendImpulse v4 Build Script (Windows)
REM ========================================
REM
REM Expected Performance:
REM   Gross Sharpe: 0.483
REM   Net Sharpe: 0.421 @ 3bp
REM   Turnover: ~630x
REM   Activity: ~90%
REM
REM ========================================

echo.
echo ========================================
echo Building TrendImpulse v4 (Copper)
echo ========================================
echo.

python src\cli\build_trendimpulse_v4.py ^
    --csv Data\copper\pricing\canonical\copper_lme_3mo.canonical.csv ^
    --config Config\Copper\trendimpulse_v4.yaml ^
    --outdir outputs\Copper\TrendImpulse_v4

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
echo Results saved to: outputs\Copper\TrendImpulse_v4
echo.
echo Next steps:
echo   1. Review daily_series.csv for full backtest
echo   2. Check summary_metrics.json for performance
echo   3. Compare vs TrendImpulse v3
echo   4. Test in 3-sleeve portfolio blend
echo.

pause