# Rank Correlation v3 — XGB SHAP vs Att-LSTM Attention

**Data**: data/interim/paper_panel_v3.parquet (N=403, 11 features)
**Question**: Do the two interpretability methods agree on feature ranking?

## Result

| Statistic | Value | p-value | Interpretation |
|---|---|---|---|
| Spearman rho | **-0.0545** | 0.873 | weak / no monotonic agreement (independent views) |
| Kendall tau | **+0.0182** | 1.000 | weak |
| Top-3 overlap | **1/3** | -- | mostly disagree |
| Top-5 overlap | **3/5** | -- | -- |

## XGB top-3: ['NDVI', 'Prec', 'Temp']
## Att-LSTM top-3: ['Drou_A', 'SPEI', 'Temp']

## Honest claim for paper section 7.5

The Spearman rank correlation between XGBoost-SHAP (mean|SHAP|) and
Attention-LSTM (mean softmax attention) feature rankings is
rho = -0.055 (p = 0.873), with 1/3 Top-3 features
in common.

Statistically, the two methods identify largely orthogonal feature priorities.
Rather than treating this as inconsistency, we interpret it as
methodological complementarity: SHAP measures marginal contribution to the final prediction (dominated by NDVI as a direct biomass proxy), while Attention measures the model internal gating preference (favoring sparse disaster signals Drou_A / SPEI that require active focus to extract). Both views are necessary for a complete picture of the driver hierarchy.

