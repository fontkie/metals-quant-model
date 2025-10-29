\# Metals Quant Model - v2.0 Infrastructure



Systematic base metals trading strategies using a two-layer architecture.



\## 🏗️ Architecture



\### Layer A: Immutable Execution Contract

\- Vol targeting, leverage caps

\- T→T+1 PnL accrual

\- Cost model (bps on Δpos)

\- \*\*Shared by all sleeves\*\*



\### Layer B: Sleeve-Specific Logic

\- Signal generation (returns pos\_raw ∈ {-1, 0, +1})

\- Strategy-specific parameters

\- Each sleeve implements unique hypothesis



\## 📊 Current Sleeves



| Sleeve | Hypothesis | Status |

|--------|------------|--------|

| \*\*CrashAndRecover\*\* | Swing structure + volume confirmation | ✅ Operational |

| \*\*HookCore\*\* | Bollinger mean-reversion + regime filters | ✅ Operational |

| \*\*MomentumTail\*\* | Trend + tail risk hedging | ✅ Operational |

| \*\*TrendCore\*\* | \[Description] | ✅ Operational |

| \*\*\[Sleeve 5]\*\* | \[Description] | ✅ Operational |



\## 🚀 Quick Start



\### Build a Sleeve

```bash

cd C:\\Code\\Metals

run\_crashandrecover.bat

```



\### Output Structure

```

outputs\\

└── Copper\\

&nbsp;   └── CrashAndRecover\\

&nbsp;       ├── daily\_series.csv

&nbsp;       └── summary\_metrics.json

```



\## 📁 Directory Structure



```

C:\\Code\\Metals\\

├── src\\

│   ├── core\\

│   │   └── contract.py          # Layer A (immutable)

│   ├── signals\\

│   │   ├── crashandrecover.py

│   │   ├── hookcore.py

│   │   └── momentumtail.py

│   └── cli\\

│       ├── build\_crashandrecover.py

│       ├── build\_hookcore\_v2.py

│       └── build\_momentumtail\_v2.py

├── Config\\

│   └── Copper\\

│       ├── crashandrecover.yaml

│       ├── hookcore.yaml

│       └── momentumtail.yaml

├── Data\\                        # Not in git (too large)

├── outputs\\                     # Not in git (generated)

├── tools\\

│   └── validate\_outputs.py

└── run\_\*.bat                    # Build scripts

```



\## 🔧 Development



\### Creating a New Sleeve



1\. \*\*Signal function:\*\* `src\\signals\\newsleeve.py`

2\. \*\*Build script:\*\* `src\\cli\\build\_newsleeve.py`

3\. \*\*Config:\*\* `Config\\Copper\\newsleeve.yaml`

4\. \*\*Batch file:\*\* `run\_newsleeve.bat`

5\. \*\*Test:\*\* Run and validate



See \[INFRASTRUCTURE\_STANDARDS.md](./INFRASTRUCTURE\_STANDARDS.md) for full details.



\### Validation



All outputs are automatically validated against the Layer A contract:

```bash

python tools\\validate\_outputs.py --outdir outputs\\Copper\\CrashAndRecover

```



\## 📖 Documentation



\- \[Infrastructure Standards](./INFRASTRUCTURE\_STANDARDS.md) - Complete technical specification

\- \[Quick Reference](./QUICK\_REFERENCE.md) - Day-to-day cheat sheet



\## 🎯 Design Principles



1\. \*\*Immutable Layer A\*\* - All sleeves use identical execution contract

2\. \*\*T→T+1 Accrual\*\* - Position at T-1 earns return at T

3\. \*\*Vol Targeting\*\* - Each sleeve scaled to target volatility

4\. \*\*Cost Awareness\*\* - Realistic transaction costs on all trades

5\. \*\*Validation First\*\* - No results trusted until validated



\## 📊 Performance Summary



| Sleeve | Sharpe | Ann. Vol | Max DD | Observations |

|--------|--------|----------|--------|--------------|

| CrashAndRecover | -0.40 | 3.83% | -37.13% | 5,690 |

| HookCore | \[TBD] | \[TBD] | \[TBD] | \[TBD] |

| MomentumTail | -0.02 | 3.50% | -18.72% | 6,698 |



\*Performance as of October 2025\*



\## 🔬 Next Steps



\- \[ ] Parameter optimization for existing sleeves

\- \[ ] Regime analysis (contango/backwardation)

\- \[ ] Expand to other metals (Aluminum, Zinc)

\- \[ ] Portfolio construction across sleeves

\- \[ ] Live trading integration



\## ⚖️ License



Proprietary - All rights reserved



\## 📧 Contact



PM: \[Your name]

