# 🧭 SEED CHAT — Metals Quant Model

Use this message whenever starting a new ChatGPT session to restore full project context.

---

## 🪜 Prompt to paste

> This is a continuation of my **"metals-quant-model"** project.  
> The repo is on GitHub: https://github.com/fontkie/metals-quant-model  
> 
> **Current baseline (Oct 2025):**
> - Project root contains `config/`, `src/`, `docs/`, `outputs/`, and `.gitignore`.
> - `config/global.yaml` defines shared settings:
>   - T + 1 execution  
>   - 10 % annual vol target (21-day lookback, cap = 3×)  
>   - 1.5 bps per-turnover cost  
>   - IS : 2008-01-01 → 2017-12-31 / OOS : 2018-01-01 → present
> - `docs/copper/` is the master folder for the Copper strategy, with three sleeves:
>   - **pricing/** — frozen v0.3.0 (trend + hook + RSI on copper 3-month)  
>   - **stocks/** — supply-side sentiment (LME stocks, in calibration)  
>   - **positioning/** — fund/manager positioning (contrarian, early stage)
> - Core scripts in `src/`:  
>   `build_sleeves.py`, `grid_optimize_combo.py`, `optimise_weights.py`, `show_layout.py`
> - `outputs/` and `data/` are local and ignored by Git; they contain rebuildable CSVs.
> - `.gitkeep` files preserve structure for `outputs/`, `data/`, `database/`, `Copper/`.

> Please confirm that this baseline (Copper v0.3.0 frozen) is consistent and reproducible.  
> Then summarise the repo structure, key scripts, and how to rebuild the Pricing sleeve and Top-10 grid from a clean clone.

---

## 🧱 Purpose

This acts as a **line-in-the-sand reference point** for the project.  
When pasted into a new chat, it restores the shared understanding of:

1. Repository structure  
2. Naming conventions  
3. Active Copper sleeves and current version  
4. Expected reproducibility workflow  

Keep this file updated each time a new major version or sleeve is frozen  
(e.g. *Copper v0.4.0*, *Zinc v0.1.0*, etc.).

---

## 🔄 Layout Sync – Option C (GitHub or local helper)

To share or confirm your live folder structure with ChatGPT:

### 🔸 Option 1 – Quick command
Run the helper script and save the output to a text file:
```bash
python src/show_layout.py --all > repo_structure.txt
