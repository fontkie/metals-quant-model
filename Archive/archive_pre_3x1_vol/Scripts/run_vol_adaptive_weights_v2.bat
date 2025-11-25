@echo off
REM =================================================================
REM Build Adaptive Vol Weights v2
REM Optimizes weights per IV regime (3x1 classification)
REM 
REM Outputs:
REM   - vol_adaptive_weights_{timestamp}.yaml (for code)
REM   - vol_adaptive_weights_{timestamp}.csv (for verification)
REM   - vol_adaptive_weights_latest.yaml (convenience)
REM =================================================================

echo.
echo ===================================================================
echo ADAPTIVE VOL WEIGHTS BUILDER v2.0
echo ===================================================================
echo.
echo This optimizes weights per IV regime (Low/Medium/High).
echo Method: Maximum Sharpe per regime with floor/ceiling per sleeve type
echo Period: 2011-2018 (In-Sample, IV data required)
echo Regime Lag: T-1 (conservative - no forward bias on IV publication)
echo.

REM Change to project root
cd /d "%~dp0.."

REM Run the Python script
python tools\build_vol_adaptive_weights_v2.py ^
    --config "Config\Copper\vol_adaptive_portfolio_v2.yaml" ^
    --iv-file "Data\Copper\pricing\canonical\copper_lme_3mo_impliedvol.canonical.csv" ^
    --outdir "outputs\Copper\VolAdaptive" ^
    --start-date 2011-07-01 ^
    --end-date 2018-12-31 ^
    --lookback 252 ^
    --low-pct 0.33 ^
    --high-pct 0.67 ^
    --regime-lag 0
REM *** TO TEST SAME-DAY (T) CLASSIFICATION: Change --regime-lag 1 to --regime-lag 0 ***

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Adaptive weight optimization failed!
    pause
    exit /b 1
)

echo.
echo ===================================================================
echo Adaptive weights optimized and saved!
echo Check: outputs\Copper\VolAdaptive\vol_adaptive_weights_latest.csv
echo.
echo Next: Run run_vol_adaptive_portfolio_v2.bat to build portfolio
echo ===================================================================
echo.

pause