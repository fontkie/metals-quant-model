@echo off
cd /d %~dp0\..
set PYTHONPATH=%CD%
echo ========================================
echo Building Adaptive Portfolio
echo ========================================
echo.
python src\cli\build_adaptive_portfolio.py ^
    --config Config\Copper\portfolio_optimized.yaml ^
    --outdir outputs\Copper\AdaptivePortfolio ^
    --compare-static

if %errorlevel% neq 0 (
    echo.
    echo ❌ Build failed!
    pause
    exit /b 1
)

echo.
echo ✅ Build complete!
echo.
pause