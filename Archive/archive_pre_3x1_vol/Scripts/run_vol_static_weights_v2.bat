@echo off
REM =================================================================
REM Build Static Vol Weights v2
REM Optimizes weights for N sleeves from config with constraints
REM 
REM Outputs:
REM   - vol_static_weights_{timestamp}.yaml (for code)
REM   - vol_static_weights_{timestamp}.csv (for verification)
REM   - vol_static_weights_latest.yaml (convenience symlink)
REM =================================================================

echo.
echo ===================================================================
echo STATIC VOL WEIGHTS BUILDER v2.0
echo ===================================================================
echo.
echo This optimizes weights for all sleeves in config with constraints.
echo Method: Maximum Sharpe with floor/ceiling per sleeve type
echo Period: 2003-2018 (In-Sample)
echo.

REM Change to project root
cd /d "%~dp0.."

REM Run the Python script
python tools\build_vol_static_weights_v2.py ^
    --config "Config\Copper\vol_static_portfolio_v2.yaml" ^
    --outdir "outputs\Copper\VolStatic" ^
    --method max_sharpe ^
    --start-date 2003-01-01 ^
    --end-date 2018-12-31

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Weight optimization failed!
    pause
    exit /b 1
)

echo.
echo ===================================================================
echo Weights optimized and saved!
echo Check: outputs\Copper\VolStatic\vol_static_weights_latest.csv
echo.
echo Next: Run run_vol_static_portfolio.bat to build portfolio
echo ===================================================================
echo.

pause