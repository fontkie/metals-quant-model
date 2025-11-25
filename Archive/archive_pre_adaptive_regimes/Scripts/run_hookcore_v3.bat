@echo off
echo ========================================
echo Building HookCore v3.0 (Copper)
echo ========================================
echo.
echo Regime-aware mean reversion strategy
echo - Longs only (asymmetric alpha)
echo - Wider bands (20d/3.0sigma)
echo - Tier 1 safety filters
echo.

python src\cli\build_hookcore_v3.py ^
    --csv-price Data\copper\pricing\canonical\copper_lme_3mo.canonical.csv ^
    --csv-stocks Data\copper\pricing\canonical\copper_lme_total_stocks.canonical.csv ^
    --csv-iv Data\copper\pricing\canonical\copper_lme_1mo_impliedvol.canonical.csv ^
    --csv-fut-3mo Data\copper\pricing\canonical\copper_lme_3mo_fut.canonical.csv ^
    --csv-fut-12mo Data\copper\pricing\canonical\copper_lme_12mo_fut.canonical.csv ^
    --config Config\Copper\hookcore_v3.yaml ^
    --outdir outputs\Copper\HookCore_v3

if %errorlevel% neq 0 (
    echo.
    echo ❌ Build failed!
    pause
    exit /b 1
)

echo.
echo ✅ Build complete! Validating outputs...
echo.

python tools\validate_outputs.py --outdir outputs\Copper\HookCore_v3

if %errorlevel% neq 0 (
    echo.
    echo ⚠️ Validation failed! Check errors above.
    pause
    exit /b 1
)

echo.
echo ========================================
echo HookCore v3.0 Build Successful
echo ========================================
echo.
echo View results:
echo   outputs\Copper\HookCore_v3\daily_series.csv
echo   outputs\Copper\HookCore_v3\summary_metrics.json
echo.

pause