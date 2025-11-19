@echo off
REM run_rangefader_v4.bat
REM Build RangeFader v4 - Mean Reversion for Choppy Markets
REM
REM Usage: Double-click this file or run from command line
REM Prerequisites: Python 3.x with pandas, numpy, pyyaml
REM
REM CRITICAL: V4 requires OHLC data (close, high, low) for ADX calculation

echo ========================================
echo Building RangeFader v4
echo Mean Reversion for Choppy Markets
echo 4-Layer Architecture with ADX Filter
echo ========================================
echo.

REM Run the build script with OHLC data
REM Note: Close uses standard 3mo file, high/low have suffix
python src\cli\build_rangefader_v4.py ^
    --csv-close Data\copper\pricing\canonical\copper_lme_3mo.canonical.csv ^
    --csv-high Data\copper\pricing\canonical\copper_lme_3mo_high.canonical.csv ^
    --csv-low Data\copper\pricing\canonical\copper_lme_3mo_low.canonical.csv ^
    --config Config\Copper\rangefader_v4.yaml ^
    --outdir outputs\Copper\RangeFader_v4

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
echo Outputs saved to: outputs\Copper\RangeFader_v4\
echo   - daily_series.csv
echo   - summary_metrics.json
echo   - diagnostics.json
echo   - vol_diagnostics.csv
echo.
echo Expected Performance (V4):
echo   - Overall Net Sharpe: ~0.30 @ 3bps
echo   - In-Regime Sharpe: ~1.32 @ 3bps (when ADX ^< 17)
echo   - Turnover: ~70x
echo   - Activity: ~13.4%% (only in choppy markets)
echo.
echo Key Feature:
echo   V4 only trades when ADX ^< 17 (choppy/ranging markets)
echo   Goes FLAT when ADX ^>= 17 (trending markets)
echo   Perfect complement to TrendImpulse V6 (ADX ^>= 20)
echo.
echo Portfolio Context:
echo   - RangeFader: Dominates choppy (ADX ^< 17, +1.32 Sharpe)
echo   - TrendImpulse V6: Dominates trends (ADX ^>= 20, +0.42 Sharpe)
echo   - Expected Combined Sharpe: 0.75-0.85
echo.
echo Next steps:
echo   1. Review summary_metrics.json
echo   2. Check vol_diagnostics.csv for vol targeting accuracy
echo   3. Compare vs TrendImpulse v6
echo   4. Test regime-adaptive portfolio blend
echo.

pause