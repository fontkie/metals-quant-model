@echo off
echo ========================================
echo Converting Excel to Canonical CSVs
echo ========================================
python tools\make_canonical.py

if %errorlevel% neq 0 (
    echo.
    echo ❌ Conversion failed!
    pause
    exit /b 1
)

echo.
echo ✅ Canonical CSVs created successfully!
echo.
echo Files created in: Data\copper\pricing\canonical\
echo.
pause