@echo off
REM ========================================
REM TrendImpulse v3 Build Script (Windows)
REM ========================================
REM
REM Expected Performance:
REM   Sharpe: 0.24 (unconditional)
REM   Sharpe: 0.50 (in low vol regimes)
REM   Max DD: -36.78%
REM   Annual Vol: ~9.6%
REM   Activity: 92.5%
REM
REM Strategy: 20-day momentum with minimal filtering
REM - Nearly always-on (92.5% activity)
REM - Complements TrendCore (faster, different regimes)
REM - Simple and robust (2 parameters only)
REM
REM ========================================

echo.
echo ========================================
echo Building TrendImpulse v3 (Copper)
echo ========================================
echo.

REM Change to script directory
cd /d "%~dp0"

REM Run build script with arguments
python src\cli\build_trendimpulse_v3.py ^
    --csv Data\copper\pricing\canonical\copper_lme_3mo.canonical.csv ^
    --config Config\Copper\trendimpulse_v3.yaml ^
    --outdir outputs\Copper\TrendImpulse_v3

if %errorlevel% neq 0 (
    echo.
    echo ========================================
    echo Build FAILED!
    echo ========================================
    echo.
    echo Common issues:
    echo   - Check that Data\copper\pricing\canonical\copper_lme_3mo.canonical.csv exists
    echo   - Check that Config\Copper\trendimpulse_v3.yaml exists
    echo   - Check that src\signals\trendimpulse_v3.py exists
    echo   - Check that src\core\contract.py exists
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo Build COMPLETE!
echo ========================================
echo.
echo Results saved to: outputs\Copper\TrendImpulse_v3
echo.
echo Files created:
echo   - daily_series.csv (full backtest results)
echo   - summary_metrics.json (performance metrics)
echo.
echo Performance Summary:
echo   - Sharpe Ratio: 0.24 (unconditional)
echo   - Low Vol Sharpe: 0.50 (excellent!)
echo   - Activity Rate: 92.5%% (nearly always-on)
echo   - Strategy complements TrendCore
echo.
echo Next steps:
echo   1. Review daily_series.csv for full backtest
echo   2. Check summary_metrics.json for performance
echo   3. Analyze performance by volatility regime
echo   4. Compare correlation with TrendCore
echo   5. Test combined TrendCore + TrendImpulse portfolio
echo.

pause