# Strict CV v3 — XGB R^2 in 4 cross-validation schemes

**Data**: data/interim/paper_panel_v3.parquet (N=403 = 31 provinces x 13 years)
**Target**: `yield_kg_per_ha` (real yield kg/ha)
**Features**: 11 (Irr, Flood_R, Sun, Temp, SPEI, Prec, Mech, Fert, Drou_A, Flood_A, NDVI)

## Headline result

| Split | R^2 stat | RMSE (kg/ha) | folds | What it tests |
|---|---|---|---|---|
| Random 8:2 | mean **0.9072** +/- 0.0383 | 312.5 | 10 seeds | Paper protocol — same provinces in train & test |
| Leave-Province-Out | median **-16.835**, mean -176.9 (huge variance) | 825 | 31 | Generalization to unseen province |
| Leave-Year-Out | mean **0.8943** +/- 0.1038 | 296.4 | 13 | Generalization to unseen year |
| Stratified 5-fold | mean **0.9091** +/- 0.0268 | 311.2 | 5 | Mixed unseen (province, year) rows |

## Leave-Province-Out per-fold statistics (the most damning split)

- Provinces with R^2 > 0: **1 / 31**
- Provinces with R^2 > 0.5: **0 / 31**
- Best province (highest R^2): R^2 = 0.1728
- Worst province (lowest R^2): R^2 = -4051.7
- Median R^2 across 31 folds: -16.83
- 25th-75th percentile: [-74.7, -6.32]

The huge negative R^2 values indicate the model is making predictions
far outside the actual yield range for held-out provinces — it has
literally no anchor when the target province is absent from training.

## How to read this

The Random-8:2 score 0.91 = Province memorization + time signal + climate residual.
- **Removing province → R^2 = -176 (or median -16):** all useful signal vanishes.
- **Removing year → R^2 stays ~0.89:** year/trend is NOT a meaningful driver of the score.
- **5-fold (mixed) → R^2 = 0.91:** same as random, confirming individual rows are not the issue.

→ **Essentially 100% of the headline 0.91 is attributable to learning
province-level baselines (Fert/Mech/Irr signatures that identify "this is
Henan" → "Henan averages X kg/ha"). There is no transferable climate ->
yield model.** This is consistent with N=403 and 31 distinct
cross-sectional units.

## Honest claim for paper §7.1

> The headline test R^2 of 0.907 (random 8:2, paper
> protocol) is achieved entirely via stable province-level baselines:
> when the same provinces appear in both train and test sets, the model
> identifies each province via its multivariate input signature and
> outputs that province's historical mean. Under strict leave-province-
> out CV, R^2 collapses to median -16.83 (only 1
> of 31 provinces achieve R^2 > 0); this indicates that **the 11-feature
> input does not encode a transferable climate -> yield mapping at the
> province-year level**. The 0.91 should therefore be understood as
> measuring the model's ability to memorize 31 province baselines (a
> classification-like task), not its ability to predict yield from
> climate drivers.
>
> This is not a model failure but a data limitation: N=403 with 31
> distinct cross-sectional units provides insufficient within-province
> variation for any model to disentangle climate effects from baseline
> productivity. Genuine climate -> yield prediction would require either
> (a) a finer spatial resolution (county-level), (b) longer time series
> per province, or (c) explicit pooling structure (mixed-effects).
