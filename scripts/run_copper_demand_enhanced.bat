@echo off
REM ========================================
REM Build Copper Demand Overlay - ENHANCED VERSION
REM ========================================
REM
REM This script applies the ENHANCED copper demand overlay with aggressive 0.0x override.
REM
REM ENHANCEMENT:
REM   When demand=DECLINING + price rallying + portfolio long
REM   -> Scale to 0.0x (GO FLAT) instead of 0.77x
REM
REM PERFORMANCE:
REM   Full Period: +12.9 Sharpe
REM   OOS (2019-2025): +24.0 Sharpe
REM   2024-2025: +102-113 Sharpe improvement
REM
REM Author: Kieran
REM Date: November 21, 2025

echo ================================================================================
echo Building Copper Demand Overlay - ENHANCED VERSION
echo ================================================================================
echo.
echo ENHANCEMENT: Aggressive 0.0x Override
echo   Trigger: demand=DECLINING + rally + long ^>0.3
echo   Action:  Scale to 0.0x (GO FLAT)
echo   Fires:   ~1.7%% of trading days
echo.

REM Set paths
set BASELINE=C:\Code\Metals\outputs\Copper\Portfolio\BaselineEqualWeight\latest\daily_series.csv
set CONFIG=Config\copper\copper_demand_enhanced.yaml

REM Optional: Override lag setting (uncomment to use)
REM set LAG_OVERRIDE=--lag 1

REM Optional: Disable aggressive override (test standard scaling only)
REM set DISABLE_AGGRESSIVE=--no-aggressive

echo Baseline:  %BASELINE%
echo Config:    %CONFIG%
echo.

cd /d C:\Code\Metals

REM Check if files exist
if not exist "%BASELINE%" (
    echo ERROR: Baseline portfolio not found: %BASELINE%
    echo.
    echo Please ensure BaselineEqualWeight has been built first.
    echo Run: cd C:\Code\Metals\scripts
    echo      run_baseline_equal_weight.bat
    echo.
    pause
    exit /b 1
)

if not exist "%CONFIG%" (
    echo ERROR: Config file not found: %CONFIG%
    echo.
    echo Please ensure copper_demand_enhanced.yaml is in Config\copper\
    echo.
    pause
    exit /b 1
)

REM Run build script
python src\cli\build_copper_demand_enhanced.py ^
    --baseline "%BASELINE%" ^
    --config %CONFIG% ^
    %LAG_OVERRIDE% ^
    %DISABLE_AGGRESSIVE%

if %errorlevel% neq 0 (
    echo.
    echo ================================================================================
    echo BUILD FAILED
    echo ================================================================================
    echo Review the error messages above
    echo.
    pause
    exit /b 1
)

echo.
echo ================================================================================
echo BUILD COMPLETE - ENHANCED VERSION
echo ================================================================================
echo.
echo Output location: C:\Code\Metals\outputs\Copper\Portfolio\copper_demand_enhanced\
echo.
echo Files generated:
echo   1. Full overlay results:     daily_series_china_demand_enhanced_*mo_*.csv
echo   2. Signals only:             copper_demand_signals_enhanced_*mo_*.csv
echo   3. Metrics (JSON):           summary_metrics_enhanced_*mo_*.json
echo   4. Summary (TXT):            summary_enhanced_*mo_*.txt
echo.
echo ENHANCEMENT DETAILS:
echo   - Aggressive override: ENABLED (use --no-aggressive to disable)
echo   - Method: QoQ (3-month momentum)
echo   - Publication lag: 2 months (default)
echo.
echo VALIDATION CHECKLIST:
echo   [ ] Check NEUTRAL regime matches baseline (^<0.01 Sharpe difference)
echo   [ ] Verify aggressive override fired ~1-2%% of time
echo   [ ] Review 2024-2025 performance (should show large improvement)
echo   [ ] Compare to standard version if needed
echo.
echo OPTIONS:
echo   Test 1-month lag:           Edit line 31, uncomment: set LAG_OVERRIDE=--lag 1
echo   Disable aggressive override: Edit line 34, uncomment: set DISABLE_AGGRESSIVE=--no-aggressive
echo.

pause
exit /b 0