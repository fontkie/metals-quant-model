@echo off
echo ========================================
echo BASELINE LAYER4 DEMAND PORTFOLIO
echo ========================================
echo.
echo Architecture (70/25/5):
echo   70%% - Baseline with Copper Demand Overlay
echo         (Core 3 with Layer 4 fundamental filter)
echo   25%% - TightStocks v2 (supply-side, independent)
echo   05%% - VolCore v2 (vol premium, independent)
echo.
echo Demand overlay applied to Core 3 ONLY.
echo TightStocks and VolCore are independent alpha sources.
echo.
echo Costs: Applied at portfolio level (3 bps one-way)
echo.
echo IS:  Start of data to 2018-12
echo OOS: 2019-01 to present
echo.
echo ========================================
echo.

cd /d C:\Code\Metals
call .venv\Scripts\activate

python src\cli\portfolio\build_baseline_layer4_demand.py --config Config\Copper\portfolio_baseline_layer4_demand.yaml

echo.
echo ========================================
echo COMPLETE
echo ========================================
echo.
echo Output: outputs\Copper\Portfolio\BaselineLayer4Demand\latest\
echo.
echo Next steps:
echo   - Layer4 Supply: Add TightnessIndex overlay
echo   - Layer4 Combined: Demand + Supply overlays
echo.

pause