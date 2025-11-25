@echo off
REM scripts\run_rangefader_v5_optimize.bat
REM Optimize RangeFader v5 Parameters
REM
REM Usage: Double-click this file or run from command line
REM Prerequisites: Python 3.x with pandas, numpy, pyyaml
REM
REM CRITICAL: Uses proper OHLC data for ADX calculation

echo ========================================
echo RangeFader v5 Parameter Optimization
echo ========================================
echo.
echo This will find optimal mean reversion parameters
echo using systematic grid search with IS/OOS validation.
echo.
echo In-Sample: 2000-2018 (19 years)
echo Out-of-Sample: 2019-2025 (6.9 years)
echo.
echo Parameter Space:
echo   Lookback: 30, 40, 50, 60, 70 days
echo   Entry: 0.6, 0.7, 0.8, 0.9, 1.0 std
echo   Exit: 0.2, 0.3, 0.4 std
echo   ADX: 15, 17, 20
echo.
echo Total: 225 combinations
echo Estimated Time: 7-9 minutes
echo.

REM Run optimization
python src\cli\optimize_rangefader_v5.py ^
    --csv-close "C:\Code\Metals\Data\copper\pricing\canonical\copper_lme_3mo.canonical.csv" ^
    --csv-high "C:\Code\Metals\Data\copper\pricing\canonical\copper_lme_3mo_high.canonical.csv" ^
    --csv-low "C:\Code\Metals\Data\copper\pricing\canonical\copper_lme_3mo_low.canonical.csv" ^
    --outdir outputs\Copper\RangeFader_v5_optimization ^
    --target-vol 0.10 ^
    --cost-bps 3.0

REM Check if optimization succeeded
if %errorlevel% neq 0 (
    echo.
    echo ========================================
    echo OPTIMIZATION FAILED!
    echo ========================================
    echo.
    echo Check error messages above for details.
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo OPTIMIZATION COMPLETE!
echo ========================================
echo.
echo Results saved to: outputs\Copper\RangeFader_v5_optimization\
echo   - optimization_results.csv (all 225 combinations)
echo   - optimization_summary.json (best parameters + OOS validation)
echo.
echo Next steps:
echo   1. Review optimization_summary.json for best parameters
echo   2. Check OOS/IS ratio (target: ^>0.50)
echo   3. Verify regime validation passes
echo   4. If ready, update rangefader_v5.yaml with best parameters
echo   5. Run run_rangefader_v5.bat to build with optimal params
echo.

pause