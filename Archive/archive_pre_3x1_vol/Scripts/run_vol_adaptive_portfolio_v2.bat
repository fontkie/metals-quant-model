@echo off
REM =================================================================
REM Build Adaptive Portfolio v2
REM Applies regime-specific weights to build portfolio returns
REM 
REM Reads: vol_adaptive_weights_latest.yaml
REM Outputs:
REM   - daily_series_{timestamp}.csv
REM   - summary_metrics_{timestamp}.json
REM   - daily_series_latest.csv (convenience)
REM =================================================================

echo.
echo ===================================================================
echo ADAPTIVE PORTFOLIO BUILDER v2.0
echo ===================================================================
echo.
echo Applies regime-specific weights with proper turnover costs.
echo Regime Lag: T-1 (conservative - matches weights optimization)
echo Weights from: outputs\Copper\VolAdaptive\vol_adaptive_weights_latest.yaml
echo Output to:    outputs\Copper\VolAdaptive\
echo.

REM Change to project root
cd /d "%~dp0.."

REM Run the Python script
python src\cli\build_vol_adaptive_portfolio_v2.py ^
    --config "Config\Copper\vol_adaptive_portfolio_v2.yaml" ^
    --weights "outputs\Copper\VolAdaptive\vol_adaptive_weights_latest.yaml" ^
    --iv-file "Data\Copper\pricing\canonical\copper_lme_3mo_impliedvol.canonical.csv" ^
    --outdir "outputs\Copper\VolAdaptive" ^
    --split-date 2019-01-01 ^
    --lookback 252 ^
    --low-pct 0.33 ^
    --high-pct 0.67 ^
    --regime-lag 0
REM *** TO TEST SAME-DAY (T) CLASSIFICATION: Change --regime-lag 1 to --regime-lag 0 ***
REM *** MUST MATCH THE LAG USED IN WEIGHTS OPTIMIZATION! ***

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Adaptive portfolio build failed!
    pause
    exit /b 1
)

echo.
echo ===================================================================
echo Adaptive portfolio built!
echo Check: outputs\Copper\VolAdaptive\
echo.
echo Compare IS vs OOS Sharpe for robustness check
echo Examine regime transition costs
echo ===================================================================
echo.

pause