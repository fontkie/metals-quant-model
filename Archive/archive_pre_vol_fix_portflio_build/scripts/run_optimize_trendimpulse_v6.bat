@echo off
REM scripts/run_optimize_trendimpulse_v6.bat
REM Complete TrendImpulse V6 Optimization (Both Stages)
REM
REM Runs Stage 1 (192 combos) + Stage 2 (243 combos) automatically
REM Total: 435 combinations on IN-SAMPLE data only (2000-2018)
REM Expected runtime: 25-45 minutes

echo ========================================
echo TrendImpulse V6 - Complete Optimization
echo Stage 1 + Stage 2 (Automatic)
echo ========================================
echo.
echo This will run BOTH optimization stages:
echo.
echo Stage 1: Core Parameters (192 combinations)
echo   - momentum_window: [15, 20, 25]
echo   - entry_threshold: [0.008, 0.010, 0.012, 0.015]
echo   - exit_threshold: [0.002, 0.003, 0.004, 0.005]
echo   - adx_threshold: [18, 20, 22, 25]
echo.
echo Stage 2: Regime Scaling (243 combinations)
echo   - Uses best Stage 1 params
echo   - Optimizes vol regime thresholds and scales
echo.
echo Total: 435 combinations
echo Expected runtime: 25-45 minutes
echo In-Sample: 2000-2018 ONLY
echo Out-Sample: 2019-2025 (not touched)
echo.
echo Expected results:
echo   Stage 1 IS Sharpe: 0.55-0.65
echo   Stage 2 IS Sharpe: 0.60-0.70
echo.
pause

REM Run complete optimization
python tools\optimize_trendimpulse_v6_full.py ^
    --csv-close "C:\Code\Metals\Data\copper\pricing\canonical\copper_lme_3mo.canonical.csv" ^
    --csv-high "C:\Code\Metals\Data\copper\pricing\canonical\copper_lme_3mo_high.canonical.csv" ^
    --csv-low "C:\Code\Metals\Data\copper\pricing\canonical\copper_lme_3mo_low.canonical.csv" ^
    --outdir "outputs\Copper\TrendImpulse_v6\optimization"

REM Check if optimization succeeded
if %errorlevel% neq 0 (
    echo.
    echo ========================================
    echo OPTIMIZATION FAILED!
    echo ========================================
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo OPTIMIZATION COMPLETE!
echo ========================================
echo.
echo Results saved to: outputs\Copper\TrendImpulse_v6\optimization\
echo   - stage1_full_results.csv (192 combinations)
echo   - stage2_full_results.csv (243 combinations)
echo   - optimized_params.json (final best parameters)
echo.
echo Next step: Out-of-Sample Validation
echo   Double-click: scripts\run_validate_trendimpulse_v6_oos.bat
echo.
echo CRITICAL: Run OOS validation ONCE only!
echo           Never adjust parameters after seeing OOS results!
echo.
pause