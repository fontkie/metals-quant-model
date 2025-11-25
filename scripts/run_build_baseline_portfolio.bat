@echo off
REM Build Baseline Portfolio (Equal-Weight) with Timestamp
REM Double-click this file to run the portfolio builder

echo ====================================
echo Building Baseline Portfolio
echo Equal-Weight (TM v2 + MC v2 + RF v5)
echo ====================================
echo.

REM Activate virtual environment
call .venv\Scripts\activate.bat

REM Get timestamp using PowerShell (works on all Windows)
for /f "tokens=*" %%i in ('powershell -command "Get-Date -Format 'yyyyMMdd_HHmmss'"') do set TIMESTAMP=%%i

echo Timestamp: %TIMESTAMP%
echo.

REM Run builder with timestamped output directory
python src\cli\portfolio\build_baseline_portfolio.py ^
    --config Config\Copper\portfolio\portfolio_baseline.yaml ^
    --outdir outputs\Copper\Portfolio\BaselineEqualWeight\%TIMESTAMP%

if %errorlevel% neq 0 (
    echo.
    echo ❌ Portfolio build failed!
    pause
    exit /b 1
)

echo.
echo ====================================
echo Portfolio Build Complete
echo ====================================
echo.
echo Results saved to:
echo   outputs\Copper\Portfolio\BaselineEqualWeight\%TIMESTAMP%
echo.
echo Files created:
echo   - daily_series.csv
echo   - summary_metrics.json
echo   - sleeve_attribution.json
echo   - correlation_matrix.csv
echo   - validation_report.txt
echo.
echo Sharpe target: 0.77 (achieved: see validation_report.txt)
echo.

REM Create a "latest" symlink/copy for convenience
echo Creating 'latest' reference...
xcopy /Y /Q outputs\Copper\Portfolio\BaselineEqualWeight\%TIMESTAMP%\*.* outputs\Copper\Portfolio\BaselineEqualWeight\latest\ >nul 2>&1

echo.
echo Quick access: outputs\Copper\Portfolio\BaselineEqualWeight\latest\
echo Full archive: outputs\Copper\Portfolio\BaselineEqualWeight\%TIMESTAMP%\
echo.

pause