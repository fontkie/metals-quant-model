@echo off
echo ========================================
echo Building CrashAndRecover (Copper)
echo ========================================
python src\cli\build_crashandrecover.py --csv-price Data\copper\pricing\canonical\copper_lme_3mo.canonical.csv --csv-volume Data\copper\pricing\canonical\copper_lme_3mo_volume.canonical.csv --config Config\Copper\crashandrecover.yaml --outdir outputs\Copper\CrashAndRecover

if %errorlevel% neq 0 (
    echo.
    echo ❌ Build failed!
    pause
    exit /b 1
)

echo.
echo ✅ Build complete! Validating outputs...
echo.
python tools\validate_outputs.py --outdir outputs\Copper\CrashAndRecover

pause