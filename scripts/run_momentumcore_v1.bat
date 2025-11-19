@echo off
REM run_momentumcore_v1.bat
REM Build MomentumCore v1 - 12-Month TSMOM Strategy
REM
REM Usage: Double-click this file or run from command line
REM Prerequisites: Python 3.x with pandas, numpy, pyyaml

echo ========================================
echo Building MomentumCore v1
echo 12-Month Time Series Momentum (TSMOM)
echo ========================================
echo.

REM Run the build script
python src\cli\build_momentumcore_v1.py

REM Check if build succeeded
if %errorlevel% neq 0 (
    echo.
    echo ========================================
    echo BUILD FAILED!
    echo ========================================
    echo.
    echo Check error messages above for details.
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo BUILD SUCCESSFUL!
echo ========================================
echo.
echo Outputs saved to: outputs\Copper\MomentumCore_v1\
echo   - daily_series.csv
echo   - summary_metrics.json
echo.
echo Next steps:
echo   1. Review summary_metrics.json (expected Sharpe ~0.53)
echo   2. Compare vs HookCore v4 (2.1x Sharpe improvement)
echo   3. Test in 3-sleeve portfolio blend
echo   4. Validate 50/25/25 allocation (TrendCore/TrendImpulse/MomentumCore)
echo.

pause