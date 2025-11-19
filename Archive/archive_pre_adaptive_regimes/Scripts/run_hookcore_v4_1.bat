@echo off
echo ========================================
echo Building HookCore v4.1 (Copper)
echo ========================================
echo.
echo V4.1 Changes:
echo - Academic regime filter (50th percentile - SOFT)
echo - Only trade in high-vol, choppy markets
echo - Target: 0.80+ Sharpe, 10-15%% activity
echo.

python src\cli\build_hookcore_v4_1.py ^
    --csv-price Data\copper\pricing\canonical\copper_lme_3mo.canonical.csv ^
    --csv-stocks Data\copper\pricing\canonical\copper_lme_total_stocks.canonical.csv ^
    --csv-iv Data\copper\pricing\canonical\copper_lme_1mo_impliedvol.canonical.csv ^
    --csv-fut-3mo Data\copper\pricing\canonical\copper_lme_3mo_fut.canonical.csv ^
    --csv-fut-12mo Data\copper\pricing\canonical\copper_lme_12mo_fut.canonical.csv ^
    --config Config\Copper\hookcore_v4_1.yaml ^
    --outdir outputs\Copper\HookCore_v4_1

if %errorlevel% neq 0 (
    echo.
    echo ❌ Build failed!
    echo.
    echo Common issues:
    echo   1. Check hookcore_v4_1.py is in src\signals\
    echo   2. Check hookcore_v4_1.yaml is in Config\Copper\
    echo   3. Verify data paths are correct
    pause
    exit /b 1
)

echo.
echo ✅ Build complete! Validating outputs...
echo.

python tools\validate_outputs.py --outdir outputs\Copper\HookCore_v4_1

if %errorlevel% neq 0 (
    echo.
    echo ⚠️ Validation failed! Check errors above.
    pause
    exit /b 1
)

echo.
echo ========================================
echo HookCore v4.1 Build Successful
echo ========================================
echo.
echo Expected Performance (vs v4.0):
echo   Sharpe:    0.80+ (vs 0.64 in v4.0)
echo   Activity:  10-15%% (vs 20.3%% in v4.0)
echo   Max DD:    -13%% (vs -18.7%% in v4.0)
echo   Turnover:  ~15x (vs 24.5x in v4.0)
echo.
echo View results:
echo   outputs\Copper\HookCore_v4_1\daily_series.csv
echo   outputs\Copper\HookCore_v4_1\summary_metrics.json
echo.
echo Next: Compare to baseline
echo   python tools\compare_versions.py HookCore_v4 HookCore_v4_1
echo.

pause