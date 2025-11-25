@echo off
REM run_chopcore_v1.bat
REM Build ChopCore v1 macro confusion detection system
REM 
REM Pure chop detector (NO crisis mixing)
REM Usage: Overlay to reduce exposure during macro confusion

echo ========================================
echo CHOPCORE V1 - BUILD
echo ========================================
echo.

REM Activate virtual environment
call .venv\Scripts\activate.bat

REM Run build script
python src\cli\build_chopcore_v1.py ^
    --csv-dxy "C:\Code\Metals\Data\Macro\pricing\canonical\dxy_index.canonical.csv" ^
    --csv-csi300 "C:\Code\Metals\Data\Macro\pricing\canonical\csi300_index.canonical.csv" ^
    --csv-china10y "C:\Code\Metals\Data\Macro\pricing\canonical\china_10y_rate.canonical.csv" ^
    --csv-vix "C:\Code\Metals\Data\Macro\pricing\canonical\vix_iv.canonical.csv" ^
    --csv-cny "C:\Code\Metals\Data\Macro\pricing\canonical\cny_fx.canonical.csv" ^
    --csv-cnh "C:\Code\Metals\Data\Macro\pricing\canonical\cnh_fx.canonical.csv" ^
    --csv-copper "C:\Code\Metals\Data\copper\pricing\canonical\copper_lme_3mo.canonical.csv" ^
    --config "C:\Code\Metals\Config\Copper\chopcore_v1.yaml" ^
    --outdir "C:\Code\Metals\outputs\Chop\ChopCore_v1"

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
echo Outputs saved to: C:\Code\Metals\outputs\Chop\ChopCore_v1
echo.
echo Files created:
echo   - chopcore_v1_scores.csv (daily scores)
echo   - chopcore_v1_regimes.csv (regime classifications)
echo   - chopcore_v1_diagnostics.csv (detailed diagnostics)
echo   - summary_metrics.json (performance stats)
echo.
echo Next: Integrate with CrisisCore and TightnessCore in overlay system
echo.
echo VIX Filter: Only operates when VIX in [15, 25] range
echo Outside range: Returns NORMAL (1.0x sizing)
echo.

pause