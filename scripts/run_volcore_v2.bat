@echo off
REM run_volcore_v2.bat
REM Build VolCore v2 - Fixed Vol Targeting + IS/OOS Validated

echo ========================================
echo Building VolCore v2 (Fixed)
echo ========================================
echo.
echo V1 issue: Used underlying vol for targeting
echo           Result: 6.2%% vol vs 10%% target (38%% shortfall)
echo.
echo V2 fix: Uses strategy returns vol (always_on method)
echo         IS/OOS validated: 2011-2018 IS, 2019-2025 OOS
echo.
echo Expected results:
echo   - Annual vol: 10%% +/- 15%%
echo   - Sharpe: 0.45-0.55
echo.

REM Verify Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found
    pause
    exit /b 1
)

echo Building...
echo.

python src\cli\build_volcore_v2.py ^
    --csv-price Data\copper\pricing\canonical\copper_lme_3mo.canonical.csv ^
    --csv-iv Data\copper\pricing\canonical\copper_lme_1mo_impliedvol.canonical.csv ^
    --config Config\Copper\volcore_v2.yaml ^
    --outdir outputs\Copper\VolCore_v2

if %errorlevel% neq 0 (
    echo.
    echo BUILD FAILED!
    pause
    exit /b 1
)

echo.
echo ========================================
echo BUILD SUCCESSFUL
echo ========================================
echo.
echo Output structure:
echo   outputs\Copper\VolCore_v2\
echo   +-- YYYYMMDD_HHMMSS\    (timestamped run)
echo   +-- latest\              (copy of most recent)
echo.
echo Baseline integration reads from: latest\daily_series.csv
echo.
echo VERIFICATION CHECKS:
echo   [ ] Vol should be 8.5-11.5%% (was 6.2%%)
echo   [ ] Sharpe should be 0.40-0.55
echo   [ ] "Vol error" should be less than 15%%
echo.

pause