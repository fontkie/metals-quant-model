@echo off
echo ========================================
echo Building MomentumTail (Copper)
echo ========================================
python src\cli\build_momentumtail_v2.py --csv-price Data\copper\pricing\canonical\copper_lme_3mo.canonical.csv --csv-iv Data\copper\pricing\canonical\copper_lme_1mo_impliedvol.canonical.csv --config Config\Copper\momentumtail.yaml --outdir outputs\Copper\MomentumTail

if %errorlevel% neq 0 (
    echo.
    echo ❌ Build failed!
    pause
    exit /b 1
)

echo.
echo ✅ Build complete! Validating outputs...
echo.
python tools\validate_outputs.py --outdir outputs\Copper\MomentumTail

pause