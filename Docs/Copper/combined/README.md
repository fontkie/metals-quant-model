\# CopperComposite — Frozen Baseline (v0.2.1)



\*\*Default (2025-10-10)\*\*  

\- \*\*Hook stream:\*\* `return\_biweekly`  

\- \*\*Stocks return:\*\* `pnl\_net`  

\- \*\*Combine:\*\* equal-weight on returns (0.5 / 0.5)  

\- \*\*Scaling:\*\* rolling \*\*T+1 VT\*\* — 10% annual target, 21d lookback, cap 2.5×  

\- \*\*OOS window:\*\* 2018-01-01 → present



\## Run

```powershell

cd C:\\Code\\Metals

python src\\composite\_build.py



