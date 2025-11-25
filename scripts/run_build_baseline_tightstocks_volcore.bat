@echo off
REM Build Baseline + TightStocks + VolCore Portfolio
REM Three-way combination testing with grid search

echo ================================================================================
echo BASELINE + TIGHTSTOCKS + VOLCORE THREE-WAY PORTFOLIO
echo ================================================================================
echo.

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Run the builder
python src\cli\portfolio\build_baseline_tightstocks_volcore.py

REM Check if successful
if %ERRORLEVEL% EQU 0 (
    echo.
    echo ================================================================================
    echo SUCCESS - Three-way portfolio built successfully
    echo ================================================================================
    echo.
    echo Output location: outputs\Copper\Portfolio\BaselineTightStocksVolCore\
    echo.
    echo Key files:
    echo   - validation_report.txt              : Summary and recommendations
    echo   - daily_series.csv                   : Full time series data
    echo   - weight_comparison.json             : All allocation tests
    echo   - optimal_allocation.json            : Best weights found
    echo   - three_way_correlation_matrix.csv   : Component correlations
    echo   - grid_search_results.csv            : All grid combinations
    echo.
    echo Next steps:
    echo   1. Review validation_report.txt for performance analysis
    echo   2. Check if three-way beats best two-way (target: 1.05-1.20 Sharpe^)
    echo   3. Examine period breakdown for regime-specific performance
    echo   4. Consider adding China Demand overlay
    echo   5. Implement regime-adaptive allocation
    echo.
) else (
    echo.
    echo ================================================================================
    echo ERROR - Build failed
    echo ================================================================================
    echo.
    echo Common issues:
    echo   1. Missing input files - check paths in portfolio_baseline_tightstocks_volcore.yaml
    echo   2. Column names mismatch - verify position_col and pnl_col in config
    echo   3. Date alignment issues - VolCore limits to 2011-2025
    echo   4. Grid search taking too long - reduce increment or disable
    echo.
    echo Check error messages above for details.
    echo.
)

pause