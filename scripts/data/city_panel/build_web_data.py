"""Build every artefact the demo page needs: metrics, SHAP values, tree model."""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import r2_score

warnings.filterwarnings("ignore")

PANEL = Path(r"D:\DC\deliverables\city-grain-data\主产区市级面板_2000_2024.csv")
WEB = Path(r"D:\DC\deliverables\model-demo\web")
PARAMS = dict(n_estimators=300, max_depth=5, learning_rate=0.05, subsample=0.8,
              colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=1.0, random_state=42, n_jobs=-1)
FEATURES = ["log_sown", "cropland", "temp", "prec", "dew", "lat", "lon"]
LABELS = {
    "log_sown": "播种面积（对数）", "cropland": "常用耕地面积", "temp": "年均气温",
    "prec": "年降水量", "dew": "年均露点温度", "lat": "纬度", "lon": "经度",
}
MIN_FOLD = 30


def load() -> pd.DataFrame:
    df = pd.read_csv(PANEL).rename(columns={
        "粮食产量(万吨)": "y", "农作物总播种面积(千公顷)": "sown",
        "常用耕地面积(万公顷)": "cropland", "年度平均气温(°C)": "temp",
        "年度总降水量(mm)": "prec", "年度平均露点温度(°C)": "dew",
        "产量数据来源": "source", "经度": "lon", "纬度": "lat",
        "省份": "prov", "地级市": "city", "年份": "year",
    })
    for col in ("y", "sown", "cropland", "temp", "prec", "dew", "lat", "lon"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df[(df["y"] > 0) & (df["sown"] > 0)].copy()
    df["log_sown"] = np.log1p(df["sown"])
    df["log_y"] = np.log(df["y"])
    df = df.dropna(subset=FEATURES + ["log_y"]).reset_index(drop=True)
    return df


def fit_predict(train, test, target="log_y", feats=FEATURES):
    model = xgb.XGBRegressor(**PARAMS)
    model.fit(train[feats], train[target])
    return model, model.predict(test[feats])


def lpo(df, group="prov"):
    out = []
    for value in sorted(df[group].unique()):
        test = df[df[group] == value]
        if len(test) < MIN_FOLD:
            continue
        train = df[df[group] != value]
        _, pred = fit_predict(train, test)
        out.append({
            "group": str(value), "n": int(len(test)),
            "r2": float(r2_score(test["log_y"], pred)),
        })
    return out


def dump_trees(model: xgb.XGBRegressor) -> dict:
    booster = model.get_booster()
    raw = booster.get_dump(dump_format="json", with_stats=False)
    config = json.loads(booster.save_config())
    raw_base = config["learner"]["learner_model_param"]["base_score"]
    base = float(str(raw_base).strip("[]").split(",")[0])
    trees = []
    for text in raw:
        node = json.loads(text)
        flat = []

        def walk(n):
            index = len(flat)
            flat.append(None)
            if "leaf" in n:
                flat[index] = {"v": float(n["leaf"])}
            else:
                split = str(n["split"])
                if split in FEATURES:
                    feature_index = FEATURES.index(split)
                else:
                    feature_index = int(split.lstrip("f"))
                flat[index] = {
                    "f": feature_index,
                    "t": float(n["split_condition"]),
                    "l": None, "r": None, "m": None,
                }
                children = {int(c["nodeid"]): c for c in n["children"]}
                left = walk(children[int(n["yes"])])
                right = walk(children[int(n["no"])])
                missing = left if int(n["missing"]) == int(n["yes"]) else right
                flat[index].update({"l": left, "r": right, "m": missing})
            return index

        walk(node)
        trees.append(flat)
    return {"base": base, "trees": trees, "features": FEATURES}


def walk_flat(tree: list[dict], row: list[float]) -> float:
    index = 0
    while True:
        node = tree[index]
        if "v" in node:
            return node["v"]
        value = row[node["f"]]
        if value is None or (isinstance(value, float) and np.isnan(value)):
            index = node["m"]
        elif value < node["t"]:
            index = node["l"]
        else:
            index = node["r"]


def main() -> int:
    WEB.mkdir(parents=True, exist_ok=True)
    df = load()
    print(f"rows={len(df)} provinces={df['prov'].nunique()} cities={df['city'].nunique()}")

    prov_folds = lpo(df, "prov")
    year_folds = lpo(df, "year")

    shuffled = df.sample(frac=1.0, random_state=0)
    cut = int(len(shuffled) * 0.8)
    _, rand_pred = fit_predict(shuffled.iloc[:cut], shuffled.iloc[cut:])
    rand_r2 = float(r2_score(shuffled.iloc[cut:]["log_y"], rand_pred))

    model, _ = fit_predict(df, df)
    importance = [
        {"feature": f, "label": LABELS[f], "importance": float(v)}
        for f, v in sorted(zip(FEATURES, model.feature_importances_), key=lambda x: -x[1])
    ]

    # ---- 真实 SHAP（XGBoost 内置 TreeSHAP）----
    booster = model.get_booster()
    contribs = booster.predict(xgb.DMatrix(df[FEATURES]), pred_contribs=True)
    shap = pd.DataFrame(contribs[:, :-1], columns=FEATURES)
    shap_bias = float(contribs[0, -1])
    global_shap = [
        {"feature": f, "label": LABELS[f], "mean_abs": float(np.mean(np.abs(shap[f])))}
        for f in FEATURES
    ]
    global_shap.sort(key=lambda x: -x["mean_abs"])

    # 分省平均 |SHAP|
    prov_shap = []
    for prov in sorted(df["prov"].unique()):
        mask = (df["prov"] == prov).values
        prov_shap.append({
            "province": str(prov),
            "n": int(mask.sum()),
            "shap": {f: float(np.mean(np.abs(shap.loc[mask, f]))) for f in FEATURES},
        })

    # 依赖关系：气温/降水 与对应 SHAP
    def dependence(feature: str, bins: int = 12) -> list[dict]:
        series, values = df[feature], shap[feature]
        edges = np.quantile(series, np.linspace(0, 1, bins + 1))
        edges = np.unique(edges)
        points = []
        for i in range(len(edges) - 1):
            mask = (series >= edges[i]) & (series <= edges[i + 1])
            if mask.sum() < 5:
                continue
            points.append({
                "x": float(series[mask].mean()),
                "y": float(values[mask].mean()),
                "n": int(mask.sum()),
            })
        return points

    # ---- 单样本案例（用于页面展示瀑布图）----
    sample_index = int(df[df["prov"] == "河南省"].index[0]) if (df["prov"] == "河南省").any() else 0
    sample = df.loc[sample_index]
    sample_case = {
        "province": str(sample["prov"]), "city": str(sample["city"]), "year": int(sample["year"]),
        "actual_log": float(sample["log_y"]), "actual": float(np.exp(sample["log_y"])),
        "pred_log": float(np.exp(0)), "features": {f: float(sample[f]) for f in FEATURES},
        "shap": {f: float(shap.loc[sample_index, f]) for f in FEATURES},
        "bias": shap_bias,
    }
    # 该样本的实际预测
    pred_all = model.predict(df[FEATURES])
    sample_case["pred_log"] = float(pred_all[sample_index])
    sample_case["pred"] = float(np.exp(pred_all[sample_index]))

    # ---- 树模型导出（用于浏览器内实时预测）----
    tree_model = dump_trees(model)
    check_rows = df[FEATURES].head(5).values.tolist()
    manual = []
    for row in check_rows:
        total = tree_model["base"] + sum(walk_flat(t, row) for t in tree_model["trees"])
        manual.append(total)
    diff = float(np.max(np.abs(np.array(manual) - pred_all[:5])))
    print(f"tree walk check: max |python-js| = {diff:.6f}")

    payload = {
        "meta": {
            "rows": int(len(df)),
            "provinces": int(df["prov"].nunique()),
            "cities": int(df["city"].nunique()),
            "year_min": int(df["year"].min()),
            "year_max": int(df["year"].max()),
            "features": [{"key": f, "label": LABELS[f]} for f in FEATURES],
            "min_fold": MIN_FOLD,
            "tree_check": diff,
        },
        "xgboost": {
            "prov_folds": prov_folds,
            "year_folds": year_folds,
            "random_r2": rand_r2,
            "importance": importance,
            "pooled": {
                "actual": df["log_y"].round(4).tolist(),
                "pred": np.round(pred_all, 4).tolist(),
                "prov": df["prov"].tolist(),
            },
        },
        "shap": {
            "global": global_shap,
            "by_province": prov_shap,
            "temp_curve": dependence("temp"),
            "prec_curve": dependence("prec"),
            "sample": sample_case,
        },
        "tree_model": tree_model,
    }
    (WEB / "data.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"data.json -> {(WEB / 'data.json').stat().st_size/1e6:.2f} MB")
    print("prov folds:", [(f['group'], round(f['r2'], 3)) for f in prov_folds])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
