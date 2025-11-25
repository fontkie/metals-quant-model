@echo off
REM run_tightness_index_v3.bat
REM Build Tightness Index v3 - Multi-Layer Physical Market Tightness
REM
REM Usage: Double-click this file or run from command line
REM Prerequisites: Python 3.x with pandas, numpy, pyyaml

echo ========================================
echo Building Tightness Index v3
echo Multi-Layer Physical Market Tightness
echo ========================================
echo.

REM Run the build script with all required arguments
python src\cli\build_tightness_index_v3.py ^
    --csv-lme-stocks Data\copper\pricing\canonical\copper_lme_onwarrant_stocks.canonical.csv ^
    --csv-comex-stocks Data\copper\pricing\canonical\copper_comex_stocks.canonical.csv ^
    --csv-shfe-stocks Data\copper\pricing\canonical\copper_shfe_onwarrant_stocks.canonical.csv ^
    --csv-fut-3mo Data\copper\pricing\canonical\copper_lme_3mo_fut.canonical.csv ^
    --csv-fut-12mo Data\copper\pricing\canonical\copper_lme_12mo_fut.canonical.csv ^
    --config Config\Copper\tightness_index_v3.yaml ^
    --outdir outputs\Copper\TightnessIndex_v3

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
echo Outputs saved to: outputs\Copper\TightnessIndex_v3\
echo   - tightness_index_v3_scores.csv
echo   - tightness_index_v3_diagnostics.csv
echo   - summary_metrics.json
echo.
echo Next steps:
echo   1. Review scores and patterns
echo   2. Integrate with crisis directional framework
echo   3. Backtest combined system
echo.

pause