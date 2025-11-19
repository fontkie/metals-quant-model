@echo off
REM scripts/run_validate_trendimpulse_v6_oos.bat
REM Out-of-Sample Validation
REM
REM *** RUN THIS ONCE ***
REM Tests optimized parameters on 2019-2025 data
REM Reports honest results
REM NEVER adjust parameters after this!

echo ========================================
echo TrendImpulse V6 - OOS Validation
echo *** RUN ONCE - REPORT HONESTLY ***
echo ========================================
echo.
echo WARNING: This script tests optimized parameters
echo          on UNSEEN out-of-sample data (2019-2025)
echo.
echo CRITICAL RULES:
echo   1. Run this ONCE only
echo   2. Report results honestly
echo   3. NEVER go back and adjust parameters
echo   4. These are your true expectations
echo.
echo Expected OOS Sharpe: 0.45-0.55 (if no forward bias)
echo.
pause

REM Check if optimization results exist
if not exist "outputs\Copper\TrendImpulse_v6\optimization\optimized_params.json" (
    echo ========================================
    echo ERROR: Optimization results not found!
    echo ========================================
    echo.
    echo Please run optimization first:
    echo   scripts\run_optimize_trendimpulse_v6.bat
    echo.
    pause
    exit /b 1
)

echo.
echo Last chance to back out...
echo Press Ctrl+C to cancel, or
pause

REM Run validation
python tools\validate_trendimpulse_v6_oos.py ^
    --optimized-params "outputs\Copper\TrendImpulse_v6\optimization\optimized_params.json" ^
    --csv-close "C:\Code\Metals\Data\copper\pricing\canonical\copper_lme_3mo.canonical.csv" ^
    --csv-high "C:\Code\Metals\Data\copper\pricing\canonical\copper_lme_3mo_high.canonical.csv" ^
    --csv-low "C:\Code\Metals\Data\copper\pricing\canonical\copper_lme_3mo_low.canonical.csv" ^
    --outdir "outputs\Copper\TrendImpulse_v6\optimization"

REM Check if validation succeeded
if %errorlevel% neq 0 (
    echo.
    echo ========================================
    echo VALIDATION FAILED!
    echo ========================================
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo OOS VALIDATION COMPLETE!
echo ========================================
echo.
echo Results saved to: outputs\Copper\TrendImpulse_v6\optimization\
echo   - oos_validation_report.json
echo   - daily_series_is.csv
echo   - daily_series_oos.csv
echo.
echo REMEMBER:
echo   - These are honest, unbiased results
echo   - Use OOS Sharpe for production expectations
echo   - Never adjust parameters based on OOS results
echo   - If OOS Sharpe ^< 0.30, consider simpler model
echo.
echo Next steps:
echo   1. Review oos_validation_report.json
echo   2. If acceptable (OOS Sharpe ^> 0.30):
echo      - Update trendimpulse_v6.yaml with optimized params
echo      - Run full 4-layer build with vol targeting
echo      - Integrate into portfolio
echo   3. If poor (OOS Sharpe ^< 0.30):
echo      - Consider TrendImpulse V5 (simpler, no ADX)
echo      - Or use TrendMedium V2 (already working great)
echo.
pause