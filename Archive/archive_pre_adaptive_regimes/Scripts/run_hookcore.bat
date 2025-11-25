@echo off
echo ========================================
echo Building HookCore (Copper)
echo ========================================
python src\cli\build_hookcore_v2.py --csv Data\copper\pricing\canonical\copper_lme_3mo.canonical.csv --config Config\Copper\hookcore.yaml --outdir outputs\Copper\HookCore

if %errorlevel% neq 0 (
    echo.
    echo ❌ Build failed!
    pause
    exit /b 1
)

echo.
echo ✅ Build complete! Validating outputs...
echo.
python tools\validate_outputs.py --outdir outputs\Copper\HookCore

pause