#!/usr/bin/env python3
"""临时工具：把 paper_panel_v3.parquet 灌入 backend/data/grain.db。

本项目自带的 scripts/load_panel_to_db.py 因 parquet 里的省份名带
「省/市/壮族自治区/回族自治区/维吾尔自治区/自治区」后缀而匹配失败。
这里做前缀归一化，其余逻辑与 schema.sql / panel_repo.py 保持一致。

只生成运行时数据产物 grain.db，不修改任何项目源码。
"""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
PARQUET = ROOT / "data" / "interim" / "paper_panel_v3.parquet"
DB = ROOT / "backend" / "data" / "grain.db"
SCHEMA = ROOT / "backend" / "data" / "schema.sql"

# parquet 的全称省份名 → 裸名
FULL_TO_BARE = {
    "北京市": "北京", "天津市": "天津", "河北省": "河北", "山西省": "山西",
    "内蒙古自治区": "内蒙古", "辽宁省": "辽宁", "吉林省": "吉林",
    "黑龙江省": "黑龙江", "上海市": "上海", "江苏省": "江苏", "浙江省": "浙江",
    "安徽省": "安徽", "福建省": "福建", "江西省": "江西", "山东省": "山东",
    "河南省": "河南", "湖北省": "湖北", "湖南省": "湖南", "广东省": "广东",
    "广西壮族自治区": "广西", "海南省": "海南", "重庆市": "重庆",
    "四川省": "四川", "贵州省": "贵州", "云南省": "云南", "西藏自治区": "西藏",
    "陕西省": "陕西", "甘肃省": "甘肃", "青海省": "青海",
    "宁夏回族自治区": "宁夏", "新疆维吾尔自治区": "新疆",
}

# 裸名 → 英文 slug
NAME_EN = {
    "北京": "beijing", "天津": "tianjin", "河北": "hebei", "山西": "shanxi",
    "内蒙古": "inner-mongolia", "辽宁": "liaoning", "吉林": "jilin",
    "黑龙江": "heilongjiang", "上海": "shanghai", "江苏": "jiangsu",
    "浙江": "zhejiang", "安徽": "anhui", "福建": "fujian", "江西": "jiangxi",
    "山东": "shandong", "河南": "henan", "湖北": "hubei", "湖南": "hunan",
    "广东": "guangdong", "广西": "guangxi", "海南": "hainan", "重庆": "chongqing",
    "四川": "sichuan", "贵州": "guizhou", "云南": "yunnan", "西藏": "tibet",
    "陕西": "shaanxi", "甘肃": "gansu", "青海": "qinghai", "宁夏": "ningxia",
    "新疆": "xinjiang",
}

# 裸名 → 7 大区
REGION = {
    "北京": "华北", "天津": "华北", "河北": "华北", "山西": "华北", "内蒙古": "华北",
    "辽宁": "东北", "吉林": "东北", "黑龙江": "东北",
    "上海": "华东", "江苏": "华东", "浙江": "华东", "安徽": "华东",
    "福建": "华东", "江西": "华东", "山东": "华东",
    "河南": "华中", "湖北": "华中", "湖南": "华中",
    "广东": "华南", "广西": "华南", "海南": "华南",
    "重庆": "西南", "四川": "西南", "贵州": "西南", "云南": "西南", "西藏": "西南",
    "陕西": "西北", "甘肃": "西北", "青海": "西北", "宁夏": "西北", "新疆": "西北",
}

# schema 的 YEARLY_PANEL 列 → parquet 列名
FEATURE_MAP = {
    "yield_kg_per_ha": "yield_kg_per_ha",
    "y_butter": "y_butter",
    "y_linear": "y_linear",
    "ndvi": "ndvi",
    "temp": "temp",
    "prec": "prec",
    "sun": "sun",
    "spei": "spei",
    "drou_a": "drou_a",
    "flood_a": "flood_a",
    "flood_r": "flood",   # parquet 用 flood，schema 用 flood_r
    "irr": "irr",
    "fert": "fert",
    "mech": "mech",
}


def main() -> int:
    if not PARQUET.exists():
        print(f"[FATAL] parquet 不存在: {PARQUET}")
        return 1
    df = pd.read_parquet(PARQUET)
    print(f"[load] raw shape: {df.shape}")

    df["province"] = df["province"].map(FULL_TO_BARE)
    missing = sorted(set(df["province"][df["province"].isna()]))
    if missing:
        print(f"[FATAL] 省份名不在 FULL_TO_BARE: {missing}")
        return 1

    names = set(df["province"])
    if names != set(NAME_EN.keys()):
        print(f"[FATAL] 省份集合不一致: {sorted(names ^ set(NAME_EN.keys()))}")
        return 1

    years = sorted(df["year"].unique().tolist())
    print(f"[load] years={years} rows={len(df)} provinces={len(names)}")

    # 1) 清库建表
    DB.parent.mkdir(parents=True, exist_ok=True)
    if DB.exists():
        DB.unlink()
    conn = sqlite3.connect(DB)
    schema_sql = SCHEMA.read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    print("[schema] 已执行 schema.sql")

    # 2) provinces
    prov_rows = [(n, NAME_EN[n], REGION[n]) for n in sorted(NAME_EN.keys())]
    conn.executemany(
        "INSERT INTO provinces (name, name_en, region) VALUES (?, ?, ?)", prov_rows
    )

    # 3) yearly_panel（列名大小写直接用 parquet 小写）
    cols = list(FEATURE_MAP.keys())
    insert_sql = (
        "INSERT OR REPLACE INTO yearly_panel (province, year, "
        + ", ".join(cols)
        + ") VALUES (?, ?, " + ", ".join(["?"] * len(cols)) + ")"
    )
    rows = []
    for _, r in df.iterrows():
        vals = [r["province"], int(r["year"])]
        for col in cols:
            v = r[FEATURE_MAP[col]]
            vals.append(None if pd.isna(v) else float(v))
        rows.append(tuple(vals))
    conn.executemany(insert_sql, rows)

    # 4) metadata
    md5 = hashlib.md5(PARQUET.read_bytes()).hexdigest()
    conn.executemany(
        "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
        [
            ("loaded_at", pd.Timestamp.utcnow().isoformat()),
            ("parquet_md5", md5),
            ("data_version", "v3"),
            ("rows_expected", "403"),
        ],
    )
    conn.commit()

    # 5) 校验
    n_prov = conn.execute("SELECT COUNT(*) FROM provinces").fetchone()[0]
    n_panel = conn.execute("SELECT COUNT(*) FROM yearly_panel").fetchone()[0]
    n_years = conn.execute("SELECT COUNT(DISTINCT year) FROM yearly_panel").fetchone()[0]
    print(f"[verify] provinces={n_prov} panel_rows={n_panel} years={n_years}")
    conn.close()

    if n_prov != 31 or n_panel != 403 or n_years != 13:
        print("[FATAL] 数据量校验失败")
        return 1
    print(f"[OK] grain.db 已生成: {DB}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
