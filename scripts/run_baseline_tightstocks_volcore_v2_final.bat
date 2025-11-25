@echo off
echo ========================================
echo FINAL PORTFOLIO VALIDATION (70/25/5)
echo ========================================
echo.
echo Applies FIXED weights with standard IS/OOS:
echo   - Baseline:    70%%
echo   - TightStocks: 25%% (validated IS 2011-2018)
echo   - VolCore:      5%% (10%% raw, 50%% discount)
echo.
echo IS:  2011-06 to 2018-12 (when all sleeves exist)
echo OOS: 2019-01 to present
echo.
echo ========================================
echo.

cd /d C:\Code\Metals
call .venv\Scripts\activate

python src\cli\portfolio\build_baseline_tightstocks_volcore_v2_final.py --config Config\Copper\portfolio_baseline_tightstocks_volcore_v2_final.yaml

echo.
echo ========================================
echo COMPLETE
echo ========================================
echo.
echo Output: outputs\Copper\Portfolio\BaselineTightStocksVolCore_v2_final\latest\
echo.

pause