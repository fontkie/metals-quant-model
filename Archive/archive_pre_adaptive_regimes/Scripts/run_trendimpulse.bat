@echo off
echo ========================================
echo Building TrendImpulse (Copper)
echo ========================================
python src\cli\build_trendimpulse_v2.py --csv Data\copper\pricing\canonical\copper_lme_3mo.canonical.csv --config Config\Copper\trendimpulse.yaml --outdir outputs\Copper\TrendImpulse

if %errorlevel% neq 0 (
    echo.
    echo ❌ Build failed!
    pause
    exit /b 1
)

echo.
echo ✅ Build complete! Validating outputs...
echo.
python tools\validate_outputs.py --outdir outputs\Copper\TrendImpulse

pause