@echo off
cd /d C:\Code\Metals
.\.venv\Scripts\python.exe src\build_trendimpulse.py ^
  --excel "C:\Code\Metals\Data\copper\pricing\pricing_values.xlsx" ^
  --sheet Raw ^
  --date-col Date ^
  --price-col copper_lme_3mo ^
  --symbol COPPER
echo Done (see outputs\trendimpulse\COPPER)
