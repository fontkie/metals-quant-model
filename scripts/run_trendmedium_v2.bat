@echo off
REM ========================================
REM TrendMedium v2 Build Script (Windows)
REM ========================================
REM
REM V2 CHANGES:
REM   - Added 2.5x calibration factor
REM   - Target vol: 10% (vs 4.19% in v1)
REM   - Max DD: ~-24% (true risk vs -10% in v1)
REM
REM Expected Performance:
REM   Sharpe: 0.60-0.65 (unchanged)
REM   Vol: ~10% (FIXED)
REM   Targets 2-4 month trends
REM
REM ========================================

echo.
echo ========================================
echo Building TrendMedium v2 (Copper)
echo ========================================
echo.
echo V2 Changes: Calibrated to hit 10%% vol target
echo Previous v1: 4.19%% vol (under-scaled)
echo.

python src\cli\build_trendmedium_v2.py ^
    --csv Data\copper\pricing\canonical\copper_lme_3mo.canonical.csv ^
    --config Config\Copper\trendmedium_v2.yaml ^
    --outdir outputs\Copper\TrendMedium_v2

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
echo Results saved to: outputs\Copper\TrendMedium_v2
echo.
echo Next steps:
echo   1. Review daily_series.csv
echo   2. Check summary_metrics.json
echo   3. Verify realized vol ~10%% (was 4.19%% in v1)
echo   4. Compare Sharpe (should be ~0.62, same as v1)
echo   5. Compare Max DD (will be ~-24%%, was -10%% in v1)
echo.
echo Key Validation:
echo   - If vol = 10%% and Sharpe = 0.62 â†’ SUCCESS
echo   - If vol still low â†’ increase calibration factor
echo   - If vol too high â†’ decrease calibration factor
echo.

pause