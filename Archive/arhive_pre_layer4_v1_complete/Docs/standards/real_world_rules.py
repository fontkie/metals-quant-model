# Real-World Trading Rules — Metals Models 2.0

These rules are the **source of truth** for execution, sizing, costs, and PnL across the project.  
Sleeves may **override** the defaults in their local README or config, but must state the deviation explicitly.

---

## A) Execution calendar

- **Default cadence (twice weekly):** **Monday** and **Wednesday** (business-day aware).
- **Signal origin dates:**
  - Monday trade uses **Friday close** data as origin.
  - Wednesday trade uses **Tuesday close** data as origin.
- **Pricing sleeve default (Directionals, e.g., TrendCore):** **trade on T (same-day close)**.
  - Orders are executed at (or into) the **same day’s close** (e.g., MOC/VWAP-to-close).
  - This assumes we can compute signals/sizing intraday using data available up to the close.
- **Other sleeves (e.g., some mean-revert, inventory, or cross-market):**
  - May trade on **T+1** (next day’s close) if the signal requires end-of-day confirmation or operational constraints.
  - Any such sleeve must state: `fill_timing = close_Tplus1`.

**PnL start:** The **day after the trade** (T+1). Even when we trade on T, daily PnL is computed from `pos_{t-1}`.

---

## B) Vol targeting / sizing

- **Target:** 10% annualised.
- **Estimator:** rolling **21-day** realised **simple** returns (std × √252).
- **Information timing:**
  - **Pricing default:** **use data up to T** (inclusive) since we trade at the close on T.
  - **Non-T sleeves:** use data up to **T−1** to avoid look-ahead.
- **Recompute:** **only on exec days**; **hold** size between rebalances.
- **Cap:** **2.5×** leverage at the **sizing** step. (Raising to 3× rarely helps Sharpe; review live behaviour first.)

---

## C) Costs

- **When:** only on **position-change** days (i.e., the actual fill days).
- **How:** `cost = one_way_bps × 1e-4 × |Δposition|`, with **one-way bps = 1.5** as baseline.

---

## D) PnL convention

- **Daily PnL:** `pos_{t-1} × simple_return_t` (ΔP/P).
- **No trading on non-exec days:** position is held constant.

---

## E) Sanity invariants (must always hold)

1. Turnover > 0 **only** on exec weekdays (**Mon/Wed** by default).
2. Position can **change** only on exec days; otherwise **flat**.
3. First non-zero PnL after a trade appears on the **next** business day.
4. Vol series used for sizing respects declared **info timing** (`T` for T-close sleeves, `T−1` otherwise).
5. No positions before both **z-window** and **vol lookback** warm-ups are complete.

---

## F) Sleeve-level overrides (examples)

- **TrendCore (pricing):** `fill_timing = close_T`, `vol_info = T`, Mon/Wed cadence.
- **HookCore (future):** may use `fill_timing = close_T` *or* `close_Tplus1`; if using morning/ring signals with close execution, specify clearly.
- **Inventory/Macro sleeves:** typically `close_Tplus1` (needs end-of-day confirmations).
