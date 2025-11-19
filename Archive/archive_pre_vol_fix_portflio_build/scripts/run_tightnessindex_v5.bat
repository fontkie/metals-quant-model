@echo off
REM run_tightnessindex_v5.bat
REM Build Tightness Index v5 - Enhanced Balance Layer
REM
REM Usage: Double-click this file or run from command line
REM Prerequisites: Python 3.x with pandas, numpy, pyyaml, openpyxl

echo ========================================
echo Building Tightness Index v5
echo Enhanced Balance Layer (Non-Linear)
echo ========================================
echo.

REM Run the build script with all required arguments
python src\cli\build_tightnessindex_v5.py ^
    --csv-lme-stocks Data\copper\pricing\canonical\copper_lme_onwarrant_stocks.canonical.csv ^
    --csv-comex-stocks Data\copper\pricing\canonical\copper_comex_stocks.canonical.csv ^
    --csv-shfe-stocks Data\copper\pricing\canonical\copper_shfe_onwarrant_stocks.canonical.csv ^
    --csv-fut-3mo Data\copper\pricing\canonical\copper_lme_3mo_fut.canonical.csv ^
    --csv-fut-12mo Data\copper\pricing\canonical\copper_lme_12mo_fut.canonical.csv ^
    --csv-iscg-balance Data\copper\pricing\canonical\copper_balance.canonical.csv ^
    --config Config\Copper\tightnessindex_v5.yaml ^
    --outdir outputs\Copper\TightnessIndex_v5

REM Check if build succeeded
if %errorlevel% neq 0 (
    echo.
    echo ========================================
    echo BUILD FAILED!
    echo ========================================
    echo.
    echo Check error messages above for details.
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo BUILD SUCCESSFUL!
echo ========================================
echo.
echo Outputs saved to: outputs\TightnessIndex_v5\
echo   - tightness_index_v5_scores.csv
echo   - tightness_index_v5_diagnostics.csv
echo   - summary_metrics_v5.json
echo.
echo Key V5 Enhancements:
echo   - Absolute Balance (50%%) - Where ARE we?
echo   - Velocity (30%%) - Where are we GOING?
echo   - Magnitude (20%%) - How BIG is the shock?
echo.
echo Next steps:
echo   1. Review scores and diagnostics CSVs
echo   2. Validate against historical disruption periods
echo   3. Integrate with crisis directional framework
echo.

pause