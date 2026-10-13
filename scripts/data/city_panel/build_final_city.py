"""Build the final prefecture-level panel: output + sown area + climate."""

from __future__ import annotations

import csv
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from normalize_names import norm  # noqa: E402

OFFICIAL = Path(r"D:\DC\deliverables\city-grain-data\全国市级粮食产量_长表.csv")
AGG = Path(r"D:\DC\_scan\city_agg.csv")
CLIMATE = Path(r"D:\DC\_scan\city_climate.csv")
OUT_CSV = Path(r"D:\DC\deliverables\city-grain-data\主产区市级面板_2000_2024.csv")

MAIN = ["河北省", "内蒙古自治区", "辽宁省", "吉林省", "黑龙江省", "江苏省", "安徽省",
        "江西省", "山东省", "河南省", "湖北省", "湖南省", "四川省"]
SUSPECT = {("江西省", "南昌市", 2013), ("吉林省", "白山市", 2012)}


def main() -> int:
    # 1) 官方产量
    official: dict[tuple[str, str, int], tuple[float, str]] = {}
    with OFFICIAL.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            key = (norm(row["省份"]), norm(row["地级市"]), int(row["年份"]))
            official[key] = (float(row["粮食产量(万吨)"]), row["数据来源"])
    for key in SUSPECT:
        official.pop(key, None)  # 原表列错位，剔除后由县级加总补

    # 2) 县级加总
    agg: dict[tuple[str, str, int], dict[str, float]] = {}
    with AGG.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            key = (norm(row["省份"]), norm(row["地级市"]), int(row["年份"]))
            agg[key] = {
                "grain": float(row["县级加总_粮食产量_万吨"]),
                "sown": float(row["县级加总_播种面积_千公顷"]),
                "crop": float(row["县级加总_耕地面积_公顷"]),
                "n": float(row["覆盖县数"]),
            }

    # 3) 逐市校准系数
    pairs: dict[tuple[str, str], list[float]] = defaultdict(list)
    for (prov, city, year), (value, _) in official.items():
        item = agg.get((prov, city, year))
        if item and item["grain"] > 0 and value > 0:
            pairs[(prov, city)].append(value / item["grain"])
    city_ratio = {k: statistics.median(v) for k, v in pairs.items() if len(v) >= 2}
    prov_ratio: dict[str, float] = {}
    for prov in MAIN:
        values = [r for (p, _), r in city_ratio.items() if p == prov]
        if values:
            prov_ratio[prov] = statistics.median(values)
    global_ratio = statistics.median(city_ratio.values()) if city_ratio else 1.0
    print(f"校准系数: 市级 {len(city_ratio)} 个, 省级 {len(prov_ratio)} 个, 全局 {global_ratio:.3f}")

    # 4) 气候
    climate: dict[tuple[str, str, int], tuple[float, float, float]] = {}
    if CLIMATE.exists():
        with CLIMATE.open(encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                climate[(row["省份"], row["地级市"], int(row["年份"]))] = (
                    float(row["年度平均气温(°C)"]),
                    float(row["年度总降水量(mm)"]),
                    float(row["年度平均露点温度(°C)"]),
                )
    print(f"气候记录: {len(climate)}")

    # 4b) 市级质心（气候取点坐标）
    centroid: dict[tuple[str, str], tuple[str, str]] = {}
    cities_csv = Path(r"D:\DC\_scan\cities2.csv")
    if cities_csv.exists():
        with cities_csv.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                centroid[(row["province"], row["city"])] = (row["lon"], row["lat"])

    # 5) 合并
    def real_city(name: str) -> bool:
        """剔除省直管县被误聚成“省名”的伪地级单位。"""
        if name == "" or name.endswith(("省", "自治区", "直辖市")):
            return False
        return name.endswith(("市", "盟", "地区", "自治州"))

    keys = [k for k in (set(official) | set(agg)) if k[0] in MAIN and real_city(k[1])]
    rows = []
    for prov, city, year in sorted(keys, key=lambda k: (MAIN.index(k[0]), k[1], k[2])):
        item = agg.get((prov, city, year))
        if (prov, city, year) in official:
            value, source = official[(prov, city, year)]
        elif item and item["grain"] > 0:
            ratio = city_ratio.get((prov, city)) or prov_ratio.get(prov) or global_ratio
            value, source = round(item["grain"] * ratio, 2), "县级加总校准估算"
        else:
            continue

        sown = item["sown"] if item else ""
        crop = item["crop"] if item else ""
        counties = int(item["n"]) if item else ""
        if sown and float(sown) > 0:
            yield_per_sown = round(value / float(sown) * 10000 / 1000, 1)
        else:
            yield_per_sown = ""
        crop_ratio = ""
        if crop and item and item["n"]:
            crop_ratio = round(float(crop) / 1e4, 1)  # 万公顷，便于与播种面积对比

        temp, prec, dew = climate.get((prov, city, year), ("", "", ""))
        lon, lat = centroid.get((prov, city), ("", ""))
        rows.append({
            "年份": year,
            "省份": prov,
            "地级市": city,
            "粮食产量(万吨)": value,
            "产量数据来源": source,
            "农作物总播种面积(千公顷)": sown,
            "常用耕地面积(万公顷)": crop_ratio,
            "单位播种面积产量(公斤/公顷)": yield_per_sown,
            "年度平均气温(°C)": temp,
            "年度总降水量(mm)": prec,
            "年度平均露点温度(°C)": dew,
            "经度": lon,
            "纬度": lat,
            "参与加总的县级单位数": counties,
        })

    headers = list(rows[0].keys())
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)

    official_n = sum(1 for r in rows if r["产量数据来源"] != "县级加总校准估算")
    years = sorted({r["年份"] for r in rows})
    print(f"行数 {len(rows)}（官方 {official_n} / 估算 {len(rows) - official_n}），年份 {years[0]}-{years[-1]}")
    print(f"-> {OUT_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
