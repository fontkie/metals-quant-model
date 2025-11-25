@echo off
REM =================================================================
REM Run Vol Adaptive Portfolio - Proper Portfolio-Level Costs
REM 
REM Location: C:\Code\Metals\scripts\run_vol_adaptive_portfolio.bat
REM Calls: C:\Code\Metals\src\cli\build_vol_adaptive_portfolio.py
REM Output: outputs\Copper\VolAdaptive\
REM =================================================================

echo.
echo ===================================================================
echo VOL ADAPTIVE PORTFOLIO - Regime-Aware with Portfolio-Level Costs
echo ===================================================================
echo.
echo Building vol adaptive portfolio with:
echo   - Regime detection (vol x trend)
echo   - Dynamic weight blending
echo   - Proper portfolio-level cost tracking
echo.
echo Config: Config\Copper\vol_adaptive_portfolio.yaml
echo Output: outputs\Copper\VolAdaptive\
echo.

REM Change to project root
cd /d "%~dp0.."

REM Run the Python script
python src\cli\build_vol_adaptive_portfolio.py ^
    --config "Config\Copper\vol_adaptive_portfolio.yaml" ^
    --outdir "outputs\Copper\VolAdaptive"

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
echo Next: Compare with static baseline (run_vol_static.bat)
echo ===================================================================
echo.

pause