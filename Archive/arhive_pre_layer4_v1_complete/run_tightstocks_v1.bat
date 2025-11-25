@echo off
REM run_tightstocks_v1.bat
REM Build TightStocks v1 - Continuous IIS Signal

echo ========================================
echo Building TightStocks v1
echo Continuous Inventory Investment Surprise
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
python src\cli\build_tightstocks_v1.py --csv-price Data\copper\pricing\canonical\copper_lme_3mo.canonical.csv --csv-lme-stocks Data\copper\pricing\canonical\copper_lme_onwarrant_stocks.canonical.csv --csv-comex-stocks Data\copper\pricing\canonical\copper_comex_stocks.canonical.csv --csv-shfe-stocks Data\copper\pricing\canonical\copper_shfe_onwarrant_stocks.canonical.csv --config Config\Copper\tightstocks_v1.yaml --outdir outputs\Copper\TightStocks_v1

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
echo Outputs: outputs\Copper\TightStocks_v1\
echo.
echo Next steps:
echo 1. Verify Sharpe ~0.65-0.77
echo 2. Check correlation with baseline ^<0.10
echo 3. Re-optimize 3x1 weights with 4 sleeves
echo 4. Set allocation (15-33%% weight)
echo.

pause