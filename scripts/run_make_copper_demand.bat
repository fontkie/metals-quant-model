@echo off
REM Run make_canonical_copper_demand.py to process copper demand data into canonical format
REM
REM Input:  C:\Code\Metals\Data\copper\fundamentals\china_demand_values.xlsx
REM Output: C:\Code\Metals\Data\copper\fundamentals\canonical\copper_demand_proxy.canonical.csv

echo ========================================
echo Converting Copper Demand Data to Canonical Format
echo ========================================
echo.

cd /d C:\Code\Metals

REM Call the Python script from tools directory
python tools\make_canonical_copper_demand.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Script failed with error code %ERRORLEVEL%
    echo.
    echo Common issues:
    echo   - Excel file not found at expected location
    echo   - Sheet name incorrect (check if sheet is named "Raw")
    echo   - Column name mismatch (check if date column is "Date")
    echo   - Missing python packages (pandas, openpyxl)
    echo.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ========================================
echo Success! Canonical file created.
echo ========================================
echo.
echo Output: Data\copper\fundamentals\canonical\copper_demand.canonical.csv
echo.
echo Next steps:
echo   1. Verify the canonical CSV (open in Excel/text editor)
echo   2. Run: scripts\run_copper_demand.bat
echo.

pause