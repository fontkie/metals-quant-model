@echo off
REM run_trendimpulse_v5.bat
REM Build TrendImpulse v5 - Quality Momentum with 4-Layer Architecture
REM
REM Usage: Double-click this file or run from command line
REM Prerequisites: Python 3.x with pandas, numpy, pyyaml

echo ========================================
echo Building TrendImpulse v5
echo Quality Momentum with Regime Scaling
echo 4-Layer Architecture
echo ========================================
echo.

REM Run the build script
python src\cli\build_trendimpulse_v5.py ^
    --csv Data\copper\pricing\canonical\copper_lme_3mo.canonical.csv ^
    --config Config\Copper\trendimpulse_v5.yaml ^
    --outdir outputs\Copper\TrendImpulse_v5

REM Check if build succeeded
if %errorlevel% neq 0 (
    echo.
    echo ========================================
    echo BUILD FAILED!
    echo ========================================
    echo.
    echo Check error messages above for details.
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo BUILD SUCCESSFUL!
echo ========================================
echo.
echo Outputs saved to: outputs\Copper\TrendImpulse_v5\
echo   - daily_series.csv
echo   - summary_metrics.json
echo   - diagnostics.json
echo   - vol_diagnostics.csv
echo.
echo Expected Performance:
echo   - Gross Sharpe: ~0.48
echo   - Net Sharpe: ~0.42 @ 3bps
echo   - Turnover: ~630x (high but profitable)
echo   - Activity: ~90%
echo.
echo Next steps:
echo   1. Review summary_metrics.json
echo   2. Check vol_diagnostics.csv for vol targeting accuracy
echo   3. Compare vs TrendImpulse v4
echo   4. Test in 3-sleeve portfolio blend
echo.

pause