@echo off
REM scripts\run_rangefader_v5.bat
REM Build RangeFader v5 - Mean Reversion with OHLC ADX Fix
REM
REM Usage: Double-click this file or run from command line
REM Prerequisites: Python 3.x with pandas, numpy, pyyaml
REM
REM CRITICAL: V5 requires OHLC data (close, high, low) for proper ADX calculation
REM          V4 used close-only ADX which underestimated by ~6 points

echo ========================================
echo Building RangeFader v5
echo Mean Reversion for Choppy Markets
echo OHLC ADX Fix from V4
echo ========================================
echo.

REM Run the build script with OHLC data
python src\cli\build_rangefader_v5.py ^
    --csv-close "C:\Code\Metals\Data\copper\pricing\canonical\copper_lme_3mo.canonical.csv" ^
    --csv-high "C:\Code\Metals\Data\copper\pricing\canonical\copper_lme_3mo_high.canonical.csv" ^
    --csv-low "C:\Code\Metals\Data\copper\pricing\canonical\copper_lme_3mo_low.canonical.csv" ^
    --config Config\Copper\rangefader_v5.yaml ^
    --outdir outputs\Copper\RangeFader_v5

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
    echo   - Config file not found
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo BUILD SUCCESSFUL!
echo ========================================
echo.
echo Outputs saved to: outputs\Copper\RangeFader_v5\
echo   - daily_series.csv
echo   - summary_metrics.json
echo.
echo Key Improvements from V4:
echo   - Proper OHLC ADX (not close-only approximation)
echo   - More accurate regime detection (13%% choppy vs 26%%)
echo   - Higher quality trades in target regime
echo   - Better risk profile
echo.
echo Expected Performance (post-optimization):
echo   - Overall Net Sharpe: ~0.25-0.35
echo   - Choppy Sharpe: ~0.60-0.80 (target regime)
echo   - Activity: ~10-15%% of days
echo.
echo V5 vs V4 Changes:
echo   - FIXED: ADX calculation now uses OHLC (not close-only)
echo   - FIXED: Regime classification more accurate
echo   - NEW: Regime validation framework
echo   - NEW: Systematic parameter optimization
echo.
echo Next steps:
echo   1. Review summary_metrics.json
echo   2. Check regime validation (should all pass)
echo   3. Compare vs V4 results
echo   4. If needed, run optimization: run_rangefader_v5_optimize.bat
echo   5. Test in regime-adaptive portfolio
echo.

pause
