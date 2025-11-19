@echo off
echo ========================================
echo Building HookCore v4.0 (Copper)
echo ========================================
echo.
echo V4 Changes:
echo - Hold period: 5 days --^> 3 days
echo - KEEP V3 BB params (5d/1.5sigma)
echo - KEEP V3 filters (all work!)
echo.

python src\cli\build_hookcore_v4.py ^
    --csv-price Data\copper\pricing\canonical\copper_lme_3mo.canonical.csv ^
    --csv-stocks Data\copper\pricing\canonical\copper_lme_total_stocks.canonical.csv ^
    --csv-iv Data\copper\pricing\canonical\copper_lme_1mo_impliedvol.canonical.csv ^
    --csv-fut-3mo Data\copper\pricing\canonical\copper_lme_3mo_fut.canonical.csv ^
    --csv-fut-12mo Data\copper\pricing\canonical\copper_lme_12mo_fut.canonical.csv ^
    --config Config\Copper\hookcore_v4.yaml ^
    --outdir outputs\Copper\HookCore_v4

if %errorlevel% neq 0 (
    echo.
    echo ❌ Build failed!
    echo.
    echo Common issues:
    echo   1. Integration bug - positions not reaching contract
    echo   2. Check if pos_raw column is set correctly
    echo   3. See QUICK_START.md for debugging steps
    pause
    exit /b 1
)

echo.
echo ✅ Build complete! Validating outputs...
echo.

python tools\validate_outputs.py --outdir outputs\Copper\HookCore_v4

if %errorlevel% neq 0 (
    echo.
    echo ⚠️ Validation failed! Check errors above.
    pause
    exit /b 1
)

echo.
echo ========================================
echo HookCore v4.0 Build Successful
echo ========================================
echo.
echo Expected Performance:
echo   Sharpe:    0.58-0.64 (vs 0.51 in V3)
echo   Return:    5-6%%
echo   Vol:       9-10%%
echo   Turnover:  ~24x
echo.
echo View results:
echo   outputs\Copper\HookCore_v4\daily_series.csv
echo   outputs\Copper\HookCore_v4\summary_metrics.json
echo.
echo Note: If Sharpe is much lower than 0.58, there's likely
echo       an integration bug. See QUICK_START.md for debugging.
echo.

pause