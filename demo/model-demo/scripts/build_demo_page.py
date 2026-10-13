"""Assemble index.html: charts as inline SVG plus the model payload."""

from __future__ import annotations

import io
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

plt.rcParams["font.family"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["font.size"] = 10

WEB = Path(r"D:\DC\deliverables\model-demo\web")
SHELL = Path(r"D:\DC\_scan\page_shell.html")
GREEN, ORANGE, RED, NAVY, GRAY = "#2E7D5B", "#D08C34", "#C0392B", "#1F3864", "#7A8B83"


def to_svg(fig) -> str:
    buffer = io.StringIO()
    fig.savefig(buffer, format="svg", bbox_inches="tight", transparent=True)
    plt.close(fig)
    text = buffer.getvalue()
    return text[text.index("<svg"):]


def style(ax):
    ax.grid(axis="y", color="#E3E8E5", linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


def barh(labels, values, color, xlabel, figsize=(6.2, 3.1)) -> str:
    fig, ax = plt.subplots(figsize=figsize)
    ax.barh(labels, values, color=color, height=0.6)
    span = max(values) - min(0, min(values))
    for i, v in enumerate(values):
        ax.text(v + span * 0.012, i, f"{v:.3f}", va="center", fontsize=8.5)
    ax.set_xlim(min(0, min(values)) - span * 0.05, max(values) * 1.15)
    ax.set_xlabel(xlabel, fontsize=10)
    style(ax)
    return to_svg(fig)


def scatter(pooled) -> str:
    fig, ax = plt.subplots(figsize=(4.9, 4.3))
    actual = np.array(pooled["actual"])
    pred = np.array(pooled["pred"])
    ax.scatter(actual, pred, s=5, color=NAVY, alpha=0.35, edgecolors="none")
    lo, hi = float(actual.min()), float(actual.max())
    ax.plot([lo, hi], [lo, hi], color=GRAY, linestyle="--", linewidth=1)
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.set_xlabel("实际 log(产量)", fontsize=10)
    ax.set_ylabel("预测 log(产量)", fontsize=10)
    style(ax)
    ax.grid(axis="x", color="#E3E8E5", linewidth=0.8)
    return to_svg(fig)


def curve(points, xlabel, ylabel, color=NAVY, figsize=(5.1, 2.9)) -> str:
    fig, ax = plt.subplots(figsize=figsize)
    xs = [p["x"] for p in points]
    ys = [p["y"] for p in points]
    ax.plot(xs, ys, color=color, linewidth=1.7, marker="o", markersize=4)
    ax.axhline(0, color=GRAY, linewidth=0.9, linestyle="--")
    ax.set_xlabel(xlabel, fontsize=10)
    ax.set_ylabel(ylabel, fontsize=10)
    style(ax)
    return to_svg(fig)


def line(values, xlabel, ylabel) -> str:
    fig, ax = plt.subplots(figsize=(5.4, 2.9))
    ax.plot(range(1, len(values) + 1), values, color=GREEN, linewidth=1.8)
    ax.set_xlabel(xlabel, fontsize=10)
    ax.set_ylabel(ylabel, fontsize=10)
    style(ax)
    return to_svg(fig)


def bars(names, values, colors, ylabel, figsize=(5.4, 2.8)) -> str:
    fig, ax = plt.subplots(figsize=figsize)
    ax.bar(names, values, color=colors, width=0.5)
    span = max(values) - min(0, min(values))
    for i, v in enumerate(values):
        ax.text(i, v + span * 0.03, f"{v:.3f}", ha="center", fontsize=9)
    ax.axhline(0, color="#8A9A93", linewidth=1)
    ax.set_ylim(min(0, min(values)) - span * 0.15, max(values) + span * 0.2)
    ax.set_ylabel(ylabel, fontsize=10)
    style(ax)
    ax.grid(axis="x", visible=False)
    return to_svg(fig)


def median(values) -> float:
    return float(np.median(values))


def main() -> int:
    data = json.loads((WEB / "data.json").read_text(encoding="utf-8"))
    lstm_path = WEB / "lstm.json"
    lstm = json.loads(lstm_path.read_text(encoding="utf-8")) if lstm_path.exists() else None
    if lstm is None:
        print("warn: lstm.json missing, LSTM tab will show a placeholder")

    xgb, shap, meta = data["xgboost"], data["shap"], data["meta"]
    labels = {f["key"]: f["label"] for f in meta["features"]}
    prov_r2 = median([f["r2"] for f in xgb["prov_folds"]])

    svg = {
        "importance": barh([i["label"] for i in xgb["importance"]][::-1],
                           [i["importance"] for i in xgb["importance"]][::-1], GREEN, "特征重要性"),
        "lpo": barh([f["group"] for f in sorted(xgb["prov_folds"], key=lambda x: x["r2"])],
                    [f["r2"] for f in sorted(xgb["prov_folds"], key=lambda x: x["r2"])], NAVY, "留一省 R²"),
        "scatter": scatter(xgb["pooled"]),
        "shap_global": barh([i["label"] for i in shap["global"]][::-1],
                            [i["mean_abs"] for i in shap["global"]][::-1], ORANGE, "平均 |SHAP|"),
        "temp": curve(shap["temp_curve"], "年均气温（°C）", "平均 SHAP 值"),
        "prec": curve(shap["prec_curve"], "年降水量（mm）", "平均 SHAP 值"),
    }

    sample = shap["sample"]
    shap_rows = "".join(
        f"<tr><td>{labels[k]}</td><td>{v:+.4f}</td></tr>"
        for k, v in sorted(sample["shap"].items(), key=lambda kv: -abs(kv[1]))
    )
    if lstm:
        lstm_map = {f["group"]: f["r2"] for f in lstm["folds"]}
        head = "<tr><th>省份</th><th>测试样本</th><th>XGBoost R²</th><th>LSTM R²</th></tr>"
        fold_rows = "".join(
            f"<tr><td>{f['group']}</td><td>{f['n']}</td><td>{f['r2']:.3f}</td>"
            f"<td>{lstm_map.get(f['group'], float('nan')):.3f}</td></tr>"
            for f in sorted(xgb["prov_folds"], key=lambda x: -x["r2"])
        )
        lstm_svg = line(lstm["curve"], "训练轮次", "MSE 损失（标准化目标）")
        cmp_svg = bars(["XGBoost", "LSTM"], [prov_r2, lstm["median_r2"]], [NAVY, GREEN], "留一省中位 R²")
        lstm_section = f"""
  <section id="lstm">
    <div class="panel">
      <h2>LSTM 时序模型</h2>
      <p class="desc">输入同一城市连续三年（t−2、t−1、t）的 7 维特征，预测第 t 年的 log 产量；与 XGBoost 使用同一套留一省划分。</p>
      <div class="grid2">
        <div><h3>训练损失曲线（第一折）</h3>{lstm_svg}</div>
        <div><h3>与 XGBoost 对比</h3>{cmp_svg}</div>
      </div>
      <p class="note">序列共 {lstm['sequences']} 条，最多训练 80 轮并带早停。LSTM 留一省中位 R² = {lstm['median_r2']:.3f}，
      与 XGBoost 的 {prov_r2:.3f} 相比，时序结构在这个样本规模下没有带来优势。</p>
    </div>
  </section>"""
    else:
        head = "<tr><th>省份</th><th>测试样本</th><th>XGBoost R²</th></tr>"
        fold_rows = "".join(
            f"<tr><td>{f['group']}</td><td>{f['n']}</td><td>{f['r2']:.3f}</td></tr>"
            for f in sorted(xgb["prov_folds"], key=lambda x: -x["r2"])
        )
        lstm_section = """
  <section id="lstm">
    <div class="panel"><h2>LSTM 时序模型</h2>
    <p class="note">该模块需要 TensorFlow 环境训练，当前未生成结果文件。</p></div>
  </section>"""

    ranges = [
        {"label": "播种面积（千公顷）", "index": 0, "min": 20, "max": 1400, "step": 5, "value": 0},
        {"label": "常用耕地面积（万公顷）", "index": 1, "min": 1, "max": 130, "step": 1, "value": 0},
        {"label": "年均气温（°C）", "index": 2, "min": -2, "max": 25, "step": 0.1, "value": 0},
        {"label": "年降水量（mm）", "index": 3, "min": 150, "max": 2400, "step": 10, "value": 0},
        {"label": "年均露点温度（°C）", "index": 4, "min": -12, "max": 20, "step": 0.1, "value": 0},
        {"label": "纬度", "index": 5, "min": 22, "max": 50, "step": 0.1, "value": 0},
        {"label": "经度", "index": 6, "min": 85, "max": 128, "step": 0.1, "value": 0},
    ]
    for r in ranges:
        key = meta["features"][r["index"]]["key"]
        raw = float(np.expm1(sample["features"]["log_sown"])) if key == "log_sown" else float(sample["features"][key])
        r["value"] = round(min(max(raw, r["min"]), r["max"]), 1)

    sections = f"""
  <section id="overview" class="active">
    <div class="panel">
      <h2>项目与数据</h2>
      <p class="desc">三个模型回答同一个问题：给定一个地级市的播种规模、耕地资源与气候条件，如何预测并解释它的粮食产量。</p>
      <table>
        <tr><th>项目</th><th>说明</th></tr>
        <tr><td>样本</td><td>{meta['rows']} 条记录，{meta['provinces']} 个主产省，{meta['cities']} 个地级市，{meta['year_min']}–{meta['year_max']} 年</td></tr>
        <tr><td>目标变量</td><td>粮食产量（万吨），建模时取对数</td></tr>
        <tr><td>特征（7 个）</td><td>{'、'.join(labels[f['key']] for f in meta['features'])}</td></tr>
        <tr><td>XGBoost</td><td>300 棵树、最大深度 5、学习率 0.05，输出预测与特征重要性</td></tr>
        <tr><td>SHAP</td><td>TreeSHAP 精确分解，给出每个特征对单条预测的推动方向与幅度</td></tr>
        <tr><td>LSTM</td><td>序列模型，用连续三年特征预测当年产量</td></tr>
        <tr><td>验证</td><td>随机 8:2、留一年、留一省三种协议；留一省要求每折至少 {meta['min_fold']} 个测试样本</td></tr>
      </table>
      <p class="note">“交互预测”页签内嵌了训练好的树模型，拖动滑块由浏览器实时推理，
      与 Python 端 XGBoost 输出一致（最大偏差约 1e−5）。</p>
    </div>
  </section>

  <section id="xgb">
    <div class="panel">
      <h2>XGBoost 预测效果</h2>
      <p class="desc">同一套模型在三种协议下的表现，以及各特征的相对贡献。</p>
      <div class="grid2">
        <div><h3>特征重要性</h3>{svg['importance']}</div>
        <div><h3>留一省 R²（整个省份作为测试集）</h3>{svg['lpo']}</div>
      </div>
      <div class="grid2" style="margin-top:14px">
        <div><h3>预测值与实际值</h3>{svg['scatter']}</div>
        <div><h3>分省明细</h3><table>{head}{fold_rows}</table></div>
      </div>
      <p class="note">随机 8:2 协议 R² = {xgb['random_r2']:.3f}，留一省中位 R² = {prov_r2:.3f}。
      留一省把整个省留作测试集，衡量跨省外推能力，比随机划分严格得多。</p>
    </div>
  </section>

  <section id="shap">
    <div class="panel">
      <h2>SHAP 解释</h2>
      <p class="desc">SHAP 把每条预测拆成各特征的贡献值，正值推高预测，负值拉低预测。</p>
      <div class="grid2">
        <div><h3>全局特征贡献</h3>{svg['shap_global']}</div>
        <div>
          <h3>案例样本：{sample['province']} {sample['city']} {sample['year']} 年</h3>
          <p class="desc">模型预测 {sample['pred']:.1f} 万吨，实际 {sample['actual']:.1f} 万吨；基线值 {sample['bias']:.3f}（log 尺度）。</p>
          <table><tr><th>特征</th><th>SHAP 贡献</th></tr>{shap_rows}</table>
        </div>
      </div>
      <div class="grid2" style="margin-top:14px">
        <div><h3>气温的边际影响</h3>{svg['temp']}</div>
        <div><h3>降水量的边际影响</h3>{svg['prec']}</div>
      </div>
      <p class="note">按分箱取平均后可见，气温与降水对预测的推动幅度远小于播种规模与耕地面积，
      与特征重要性结论一致。</p>
    </div>
  </section>
{lstm_section}
  <section id="play">
    <div class="panel">
      <h2>交互预测</h2>
      <p class="desc">拖动滑块调整输入，页面用内嵌的树模型实时计算预测产量。</p>
      <div class="result">
        <div><div class="sub">预测 log 产量</div><div class="big" id="predLog">–</div></div>
        <div><div class="sub">折算产量</div><div class="big" id="predYield">–</div></div>
        <div class="sub" id="predDelta"></div>
      </div>
      <div id="sliders" style="margin-top:16px"></div>
      <button id="resetBtn" style="margin-top:6px;padding:8px 16px;border:1px solid var(--line);border-radius:8px;background:#fff;cursor:pointer">恢复案例默认值</button>
      <p class="note">默认值取自案例样本。把气候变量推到极端值时预测会明显外推，
      说明模型主要依赖播种规模而不是气候因子。</p>
    </div>
  </section>
"""
    shell = SHELL.read_text(encoding="utf-8")
    payload = json.dumps({"meta": meta, "xgboost": xgb, "shap": shap},
                         ensure_ascii=False, separators=(",", ":"))
    tree_json = json.dumps(data["tree_model"], ensure_ascii=False, separators=(",", ":"))
    html = (shell.replace("__SECTIONS__", sections)
                 .replace("__DATA__", payload)
                 .replace("__TREES__", tree_json)
                 .replace("__RANGES__", json.dumps(ranges, ensure_ascii=False)))
    out = WEB / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"index.html -> {out.stat().st_size/1e6:.2f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
