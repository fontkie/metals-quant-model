@echo off
REM run_crisiscore_v2.bat
REM Build CrisisCore v2 crisis detection system
REM 
REM Multi-dimensional crisis detection for directional overlay
REM Usage: Used with TightnessCore for directional amplification

echo ========================================
echo CRISISCORE V2 - BUILD
echo ========================================
echo.

REM Activate virtual environment
call .venv\Scripts\activate.bat

REM Run build script
python src\cli\build_crisiscore_v2.py ^
    --csv-hy "C:\Code\Metals\Data\Macro\pricing\canonical\us_hy_index.canonical.csv" ^
    --csv-vix "C:\Code\Metals\Data\Macro\pricing\canonical\vix_iv.canonical.csv" ^
    --config "C:\Code\Metals\Config\Copper\crisiscore_v2.yaml" ^
    --outdir "C:\Code\Metals\outputs\Crisis\CrisisCore_v2"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Build failed with error code %ERRORLEVEL%
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ========================================
echo BUILD COMPLETE
echo ========================================
echo.
echo Outputs saved to: C:\Code\Metals\outputs\Crisis\CrisisCore_v2
echo.
echo Files created:
echo   - crisiscore_v2_scores.csv (daily scores)
echo   - crisiscore_v2_regimes.csv (regime classifications)
echo   - summary_metrics.json (performance stats)
echo.
echo Next: Integrate with ChopCore and TightnessCore in overlay system
echo.

pause