@echo off
setlocal

set PY=.venv\Scripts\python.exe
set DB=Copper\quant.db
set XLS=Copper\pricing_values.xlsx
set OUT=outputs\Copper

if not exist "%PY%" goto NOENV
if not exist "%XLS%" goto NOXLS
if not exist "%OUT%" mkdir "%OUT%"

echo [Run] Loading prices...
"%PY%" src\load_data.py --xlsx "%XLS%" --db "%DB%"
if errorlevel 1 goto ERR

echo [Run] Standardising DB views...
"%PY%" src\fix_views.py --db "%DB%"
if errorlevel 1 goto ERR

echo [Run] Building signals...
"%PY%" src\build_signals.py --db "%DB%" --outdir "%OUT%"
if errorlevel 1 goto ERR

echo [Run] DB sanity checks...
"%PY%" src\test_db.py --db "%DB%" --prices-view prices_long --signals-table signals

if errorlevel 1 goto ERR

echo [Run] Backtest...
"%PY%" src\backtest_prices.py --db "%DB%" --prices-table prices_std --signals-table signals --outdir "%OUT%"
if errorlevel 1 goto ERR

echo.
echo [Run] DONE
echo Outputs: %OUT%
pause
exit /b 0

:NOENV
echo [Run] Virtual environment not found. Run setup_once.bat first.
pause
exit /b 1

:NOXLS
echo [Run] Source Excel not found at "%XLS%".
echo Ensure your file exists at Copper\pricing_values.xlsx with sheet Raw and column A named Date.
pause
exit /b 1

:ERR
echo.
echo [Run] FAILED. See the error above.
pause
exit /b 1
