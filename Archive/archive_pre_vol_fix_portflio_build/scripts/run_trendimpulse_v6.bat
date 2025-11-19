@echo off
REM run_trendimpulse_v6.bat
REM Build TrendImpulse v6 - ADX-Filtered Quality Momentum
REM
REM Usage: Double-click this file or run from command line
REM Prerequisites: Python 3.x with pandas, numpy, pyyaml
REM
REM CRITICAL: V6 requires OHLC data (close, high, low)

echo ========================================
echo Building TrendImpulse v6
echo ADX-Filtered Trending Markets Specialist
echo 4-Layer Architecture
echo ========================================
echo.

REM Run the build script with OHLC data
REM Note: Close uses standard 3mo file, high/low have suffix
python src\cli\build_trendimpulse_v6.py ^
    --csv-close Data\copper\pricing\canonical\copper_lme_3mo.canonical.csv ^
    --csv-high Data\copper\pricing\canonical\copper_lme_3mo_high.canonical.csv ^
    --csv-low Data\copper\pricing\canonical\copper_lme_3mo_low.canonical.csv ^
    --config Config\Copper\trendimpulse_v6.yaml ^
    --outdir outputs\Copper\TrendImpulse_v6

REM Check if build succeeded
if %errorlevel% neq 0 (
    echo.
    echo ========================================
    echo BUILD FAILED!
    echo ========================================
    echo.
    echo Check error messages above for details.
    echo.
    echo Common issues:
    echo   - Missing OHLC CSV files (need close, high, low)
    echo   - Incorrect file paths
    echo   - Missing Python packages (pandas, numpy, pyyaml)
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo BUILD SUCCESSFUL!
echo ========================================
echo.
echo Outputs saved to: outputs\Copper\TrendImpulse_v6\
echo   - daily_series.csv
echo   - summary_metrics.json
echo   - diagnostics.json
echo   - vol_diagnostics.csv
echo.
echo Expected Performance (V6):
echo   - Overall Net Sharpe: ~0.34 @ 3bps (72%% activity)
echo   - In-Regime Sharpe: ~0.42 @ 3bps (when ADX ^>= 20)
echo   - Turnover: ~580x (lower than V5)
echo   - Activity: ~72%% (only in trending markets)
echo.
echo V5 vs V6 Comparison:
echo   - V5: 0.369 Sharpe, 90%% activity (always on)
echo   - V6: 0.343 Sharpe, 72%% activity (trending only)
echo   - V6 In-Regime: 0.416 Sharpe (better than V5!)
echo.
echo Key Feature:
echo   V6 only trades when ADX ^>= 20 (trending markets)
echo   Goes FLAT when ADX ^< 20 (ranging markets)
echo   Perfect complement to RangeFader (ADX ^< 17)
echo.
echo Portfolio Context:
echo   - Standalone: Use V5 (higher activity)
echo   - Portfolio: Use V6 (better regime specialization)
echo   - Expected Portfolio Sharpe: 0.75-0.85
echo.
echo Next steps:
echo   1. Review summary_metrics.json
echo   2. Check vol_diagnostics.csv for vol targeting accuracy
echo   3. Compare vs TrendImpulse v5
echo   4. Build RangeFader for full regime coverage
echo   5. Test regime-adaptive portfolio blend
echo.

pause