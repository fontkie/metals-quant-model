@echo off
echo ========================================
echo BASELINE PORTFOLIO v2 - IS/OOS VALIDATED
echo ========================================
echo.
echo This runs all three validated baseline builds:
echo   1. Baseline + TightStocks (IS: 2011-2018)
echo   2. Baseline + VolCore (IS: 2017-2020, 50%% discount)
echo   3. Baseline + TightStocks + VolCore (IS: 2017-2020)
echo.
echo Methodology:
echo   - Weights optimized on IS period only
echo   - Frozen weights validated on OOS
echo   - VolCore uses shorter IS (market illiquid pre-2017)
echo   - VolCore allocation discounted 50%%
echo.
echo ========================================
echo.

cd /d C:\Code\Metals
call .venv\Scripts\activate

echo.
echo ========================================
echo 1/3: BASELINE + TIGHTSTOCKS v2
echo ========================================
python src\cli\portfolio\build_baseline_tightstocks_v2.py --config Config\Copper\portfolio_baseline_tightstocks_v2.yaml

echo.
echo ========================================
echo 2/3: BASELINE + VOLCORE v2
echo ========================================
python src\cli\portfolio\build_baseline_volcore_v2.py --config Config\Copper\portfolio_baseline_volcore_v2.yaml

echo.
echo ========================================
echo 3/3: BASELINE + TIGHTSTOCKS + VOLCORE v2
echo ========================================
python src\cli\portfolio\build_baseline_tightstocks_volcore_v2.py --config Config\Copper\portfolio_baseline_tightstocks_volcore_v2.yaml

echo.
echo ========================================
echo ALL BUILDS COMPLETE
echo ========================================
echo.
echo Outputs:
echo   outputs\Copper\Portfolio\Baseline_TightStocks_v2\
echo   outputs\Copper\Portfolio\Baseline_VolCore_v2\
echo   outputs\Copper\Portfolio\Baseline_TightStocks_VolCore_v2\
echo.
echo Each contains:
echo   - validation_summary.json (IS/OOS metrics)
echo   - daily_series.csv (daily PnLs)
echo   - weight_comparison.json (grid search results)
echo.
echo VALIDATION CRITERIA:
echo   PASS:     OOS retains >=80%% of IS Sharpe
echo   MARGINAL: OOS retains 60-80%% of IS Sharpe
echo   FAIL:     OOS retains <60%% of IS Sharpe
echo.
echo After review, archive originals:
echo   move src\cli\portfolio\build_baseline_tightstocks.py archive\
echo   move src\cli\portfolio\build_baseline_volcore.py archive\
echo   move src\cli\portfolio\build_baseline_tightstocks_volcore.py archive\
echo.

pause