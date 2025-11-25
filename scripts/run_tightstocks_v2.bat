@echo off
REM run_tightstocks_v2.bat
REM Build TightStocks v2 - Fixed Vol Targeting

echo ========================================
echo Building TightStocks v2 (Fixed)
echo Continuous IIS with proper vol targeting
echo ========================================
echo.

REM Verify Python is available
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found in PATH
    pause
    exit /b 1
)

REM Run the build script
REM Note: All data files are in Data\copper\pricing\canonical\
python src\cli\build_tightstocks_v2_fixed.py ^
    --csv-price Data\copper\pricing\canonical\copper_lme_3mo.canonical.csv ^
    --csv-lme-stocks Data\copper\pricing\canonical\copper_lme_onwarrant_stocks.canonical.csv ^
    --csv-comex-stocks Data\copper\pricing\canonical\copper_comex_stocks.canonical.csv ^
    --csv-shfe-stocks Data\copper\pricing\canonical\copper_shfe_onwarrant_stocks.canonical.csv ^
    --config Config\Copper\tightstocks_v2.yaml ^
    --outdir outputs\Copper\TightStocks_v2

REM Check if build succeeded
if %errorlevel% neq 0 (
    echo.
    echo ========================================
    echo BUILD FAILED!
    echo ========================================
    echo.
    echo Check error messages above.
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo BUILD SUCCESSFUL!
echo ========================================
echo.
echo Output structure:
echo   outputs\Copper\TightStocks_v2\
echo   +-- YYYYMMDD_HHMMSS\    (timestamped run)
echo   +-- latest\              (copy of most recent)
echo.
echo Baseline integration reads from: latest\daily_series.csv
echo.

pause