@echo off
REM =================================================================
REM Build Macro Static Weights
REM Calculates optimal static weights and saves to CSV
REM 
REM Location: C:\Code\Metals\scripts\run_macro_static_weights.bat
REM Calls: C:\Code\Metals\tools\build_macro_static_weights.py
REM Output: C:\Code\Metals\outputs\Copper\MacroRegime\macro_static_weights.csv
REM =================================================================

echo.
echo ===================================================================
echo MACRO STATIC WEIGHTS BUILDER
echo ===================================================================
echo.
echo This calculates optimal static weights for the macro-static baseline.
echo Method: Grid search over weight space (5%% increments)
echo Period: 2000-2018 (In-Sample)
echo.
echo These become the baseline weights for Path B adjustments.
echo.

REM Change to project root
cd /d "%~dp0.."

REM Run the Python script
python tools\build_macro_static_weights.py ^
    --sleeve-dir "outputs\Copper" ^
    --outdir "outputs\Copper\MacroRegime" ^
    --method grid_search ^
    --grid-step 0.05 ^
    --start-date 2000-01-01 ^
    --end-date 2018-12-31

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Weight calculation failed!
    pause
    exit /b 1
)

echo.
echo ===================================================================
echo Weights saved!
echo Check: outputs\Copper\MacroRegime\macro_static_weights.csv
echo.
echo Next: Run Path B optimizer to calculate CHOP/CRISIS multipliers
echo ===================================================================
echo.

pause