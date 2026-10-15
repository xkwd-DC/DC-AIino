"""Measure the model-side work of one /api/predict request on this machine.

The service path is: API 参数 -> to_training_keys -> 标准化 -> XGBoost 预测,
plus an 11-call perturbation loop for the per-feature contribution shown in M02.
Flask is not required to run this benchmark, so the numbers exclude HTTP
overhead and the front-end round trip; the materials report them that way.

Usage:
    python scripts/aic/bench_inference.py [--runs 5] [--panel data/interim/test_v4.csv]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import joblib
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from services.inference import TRAINING_FEATURE_ORDER, to_training_keys  # noqa: E402

API_KEYS = [
    "irr", "flood", "sun", "temp", "spei", "prec",
    "mech", "fert", "drou_a", "flood_a", "ndvi",
]


def vector(features: dict[str, float], scaler):
    row = [[float(features[k]) for k in TRAINING_FEATURE_ORDER]]
    return scaler.transform(row)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--panel", type=Path, default=ROOT / "data/interim/test_v4.csv")
    args = ap.parse_args()

    panel = pd.read_csv(args.panel)
    model = joblib.load(ROOT / "backend/models/xgb_model.pkl")
    scaler = joblib.load(ROOT / "backend/models/scaler.pkl")

    samples = panel.head(args.runs)
    warmup = {k: float(samples.iloc[0][k]) for k in API_KEYS}
    model.predict(vector(to_training_keys(warmup), scaler))  # 预热，排除首次调用的编译开销

    predict_ms: list[float] = []
    attrib_ms: list[float] = []
    outputs: list[float] = []

    for _, row in samples.iterrows():
        api = {k: float(row[k]) for k in API_KEYS}

        t0 = time.perf_counter()
        y = float(model.predict(vector(to_training_keys(api), scaler))[0])
        t1 = time.perf_counter()
        predict_ms.append((t1 - t0) * 1000)
        outputs.append(y)

        # 归因：逐特征扰动，共 11 次模型调用（与后端 /api/predict 的实现一致）
        t0 = time.perf_counter()
        for k in API_KEYS:
            probe = dict(api)
            probe[k] = api[k] * 0.9
            model.predict(vector(to_training_keys(probe), scaler))
        t1 = time.perf_counter()
        attrib_ms.append((t1 - t0) * 1000)

    summary = {
        "panel": str(args.panel.relative_to(ROOT)).replace("\\", "/"),
        "samples": len(samples),
        "predict_ms_mean": round(statistics.mean(predict_ms), 2),
        "predict_ms_min": round(min(predict_ms), 2),
        "predict_ms_max": round(max(predict_ms), 2),
        "attribution_11calls_ms_mean": round(statistics.mean(attrib_ms), 2),
        "attribution_11calls_ms_max": round(max(attrib_ms), 2),
        "predictions": [round(v, 1) for v in outputs],
        "python": sys.version.split()[0],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
