@echo off
REM Build Baseline + TightStocks Portfolio
REM Tests marginal contribution of TightStocks

echo ================================================================================
echo BASELINE + TIGHTSTOCKS PORTFOLIO BUILDER
echo ================================================================================
echo.

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Run the builder
python src\cli\portfolio\build_baseline_tightstocks.py

REM Check if successful
if %ERRORLEVEL% EQU 0 (
    echo.
    echo ================================================================================
    echo SUCCESS - Portfolio built successfully
    echo ================================================================================
    echo.
    echo Output location: outputs\Copper\Portfolio\BaselineTightStocks\
    echo.
    echo Key files:
    echo   - validation_report.txt     : Summary and recommendations
    echo   - daily_series.csv          : Full time series data
    echo   - weight_comparison.json    : All allocation tests
    echo.
    echo Next: Review validation_report.txt for marginal contribution analysis
    echo.
) else (
    echo.
    echo ================================================================================
    echo ERROR - Build failed
    echo ================================================================================
    echo.
    echo Common issues:
    echo   1. Missing input files - check paths in config
    echo   2. Column names mismatch - verify position_col and pnl_col
    echo   3. Date alignment issues - ensure overlapping dates
    echo.
    echo Check error messages above for details.
    echo.
)

pause