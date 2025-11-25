@echo off
REM ========================================
REM MomentumCore v2 Build Script (Windows)
REM ========================================
REM
REM STRATEGY: 12-month Time Series Momentum (TSMOM)
REM   - Classic momentum from Moskowitz, Ooi, Pedersen (2012)
REM   - Sign of 12-month return
REM   - Pure signal in Layer 1, vol targeting in Layer 2
REM
REM Expected Performance:
REM   Sharpe: ~0.50-0.55 (unconditional)
REM   Vol: ~10% (via closed-loop EWMA)
REM   Max DD: ~-28%
REM   Turnover: ~9x per year
REM
REM ========================================

echo.
echo ========================================
echo Building MomentumCore v2 (Copper)
echo ========================================
echo.
echo Strategy: 12-Month Time Series Momentum (TSMOM)
echo Architecture: 4-Layer (Signal -> Vol -> Blend -> Exec)
echo.

python src\cli\build_momentumcore_v2.py ^
    --csv Data\copper\pricing\canonical\copper_lme_3mo.canonical.csv ^
    --config Config\Copper\momentumcore_v2.yaml ^
    --outdir outputs\Copper\MomentumCore_v2

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
echo Results saved to: outputs\Copper\MomentumCore_v2
echo.
echo Next steps:
echo   1. Review daily_series.csv
echo   2. Check summary_metrics.json
echo   3. Verify realized vol ~10%%
echo   4. Check Sharpe ratio (~0.50-0.55 expected)
echo   5. Review diagnostics.json for full details
echo.
echo Key Validation:
echo   - If vol = 10%% and Sharpe ~0.50 -> SUCCESS
echo   - If strategy_type = always_on -> CORRECT
echo   - If turnover ~9x -> NORMAL for TSMOM
echo.

pause
