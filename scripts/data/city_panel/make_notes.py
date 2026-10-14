"""Write the 说明 sheet for the delivered workbook."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

SRC = Path(r"D:\DC\deliverables\city-grain-data\主产区市级面板_2000_2024.csv")
OUT = Path(r"D:\DC\_scan\notes.csv")


def main() -> int:
    rows = list(csv.DictReader(SRC.open(encoding="utf-8-sig")))
    sources = Counter(r["产量数据来源"] for r in rows)
    years = sorted({int(r["年份"]) for r in rows})
    latest = [r for r in rows if int(r["年份"]) >= 2023]
    provs = sorted({r["省份"] for r in latest})

    lines = [
        ["项目", "说明"],
        ["数据范围", "13 个粮食主产省的地级行政单位（市、盟、地区、自治州）"],
        ["时间范围", f"{years[0]}–{years[-1]}"] + [f"{len(rows)} 行"],
        ["粮食产量单位", "万吨"],
        ["产量来源优先级",
         "①《中国区域经济统计年鉴》地级统计资料（2004–2013）与 EPS 地级市统计年鉴库（2011–2024）的官方值；"
         "②县级统计年鉴逐县加总，并按该市重叠年份的官方值/加总值中位比值校准后的估算值"],
        ["官方值条数", str(sum(v for k, v in sources.items() if k != "县级加总校准估算"))],
        ["估算值条数", str(sources.get("县级加总校准估算", 0))],
        ["2023–2024 覆盖省份", "、".join(provs) if provs else "无"],
        ["农作物总播种面积", "千公顷，由该市所辖县级单位加总"],
        ["常用耕地面积", "万公顷，由该市所辖县级单位加总"],
        ["单位播种面积产量", "公斤/公顷 = 粮食产量 ÷ 农作物总播种面积（分母为全部作物播种面积，属广义单产）"],
        ["年度平均气温", "°C，NASA POWER 月度 T2M 取当年 12 个月平均"],
        ["年度总降水量", "mm，NASA POWER 月度降水率 × 当月天数后求和"],
        ["年度平均露点温度", "°C，NASA POWER 月度 T2MDEW 取当年 12 个月平均"],
        ["经度/纬度", "该市所辖县经纬度均值，即本次气候数据的取点位置"],
        ["已知局限 1", "县级年鉴不含市辖区，估算年份的产量略低于实际城市总量"],
        ["已知局限 2", "2023–2024 年只有 6 个主产省有官方市级数据，其余 7 省缺失"],
        ["已知局限 3", "气候为 NASA POWER 格点再分析结果，与地面站点观测存在小幅差异"],
        ["已知局限 4", "地级行政区划在 2004–2024 年间有撤并更名，跨年比较前建议先做名称归一"],
        ["生成日期", "2026-10-10"],
    ]
    with OUT.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerows(lines)
    print(f"notes rows={len(lines)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
