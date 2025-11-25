@echo off
REM =================================================================
REM Build Static Portfolio v2
REM Applies weights from YAML to build portfolio returns
REM 
REM Reads: vol_static_weights_latest.yaml
REM Outputs:
REM   - daily_series_{timestamp}.csv
REM   - summary_metrics_{timestamp}.json
REM   - daily_series_latest.csv (convenience)
REM =================================================================

echo.
echo ===================================================================
echo STATIC PORTFOLIO BUILDER v2.0
echo ===================================================================
echo.
echo Applies static weights with proper portfolio-level costs.
echo Weights from: outputs\Copper\VolStatic\vol_static_weights_latest.yaml
echo Output to:    outputs\Copper\VolStatic\
echo.

REM Change to project root
cd /d "%~dp0.."

REM Run the Python script
python src\cli\build_vol_static_portfolio_v2.py ^
    --config "Config\Copper\vol_static_portfolio_v2.yaml" ^
    --weights "outputs\Copper\VolStatic\vol_static_weights_latest.yaml" ^
    --outdir "outputs\Copper\VolStatic" ^
    --split-date 2019-01-01

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Static portfolio build failed!
    pause
    exit /b 1
)

echo.
echo ===================================================================
echo Static portfolio built!
echo Check: outputs\Copper\VolStatic\
echo.
echo Compare IS vs OOS Sharpe for robustness check
echo ===================================================================
echo.

pause