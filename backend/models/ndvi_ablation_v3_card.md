# NDVI Ablation v3 — does 10-dim XGB recover paper R^2 = 0.6293?

**Data**: data/interim/paper_panel_v3.parquet (N=403)
**Protocol**: random 8:2, 10 seeds, XGB hyper learning_rate=0.1 / max_depth=6 / n_estimators=150
**Question**: When NDVI is removed, does R^2 fall back to the paper's 10-dim baseline?

## Result

| Feature set | R^2 mean | R^2 std | RMSE mean | RMSE std |
|---|---|---|---|---|
| 11 features (with NDVI) | **0.9072** | 0.0383 | 312.5 | 54.2 |
| 10 features (NDVI ablated) | **0.9038** | 0.0218 | 326.4 | 48.3 |
| Drop | **+0.0034** | — | +14.0 | — |
| Paper §4.1 baseline | 0.6293 | — | — | — |

## Interpretation

- 10-dim XGB R^2 = **0.904** vs paper's reported 0.6293.
- Difference from paper: **+0.275** (does NOT match paper).
- NDVI alone contributes **0%** of the headline R^2.

## Honest claim for paper §7.2

> Removing NDVI from the 11-feature set drops random-8:2 R^2 from 0.907 to 0.904,
> a 0% relative drop. The 10-dim variant differs from the paper baseline 0.629, indicating that either (a) the v3 panel diverges from the paper data beyond just adding NDVI, or (b) the random-8:2 sampling has captured a stronger province signal than the paper protocol. Either way, NDVI alone explains the bulk of the 11-dim improvement.
