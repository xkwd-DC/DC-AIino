"""官网 JPG 分县播种面积表 -> PaddleOCR 左条带 -> 重建(县名, 城市, 粮食播种面积)。
输出 data/interim/sx_sown_ocr/<year>.csv (city,county,grain_sown_ha)。
"""
import os
import re
import sys
import csv
import numpy as np
from pathlib import Path

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("PADDLE_PDX_MODEL_SOURCE", "huggingface")
os.environ.setdefault("PADDLE_PDX_HUGGING_FACE_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("OMP_NUM_THREADS", "8")

import cv2
from paddleocr import PaddleOCR

ROOT = Path(r"D:\DC\DC-AIino")
IMG = ROOT / "data/raw/sx_yearbook/img"
OUT = ROOT / "data/interim/sx_sown_ocr"
OUT.mkdir(parents=True, exist_ok=True)

PRECITY = {"太原市", "大同市", "阳泉市", "长治市", "晋城市", "朔州市",
           "晋中市", "运城市", "忻州市", "临汾市", "吕梁市",
           "忻州地区", "吕梁地区", "晋中地区", "临汾地区", "运城地区"}


def strip_ws(s): return re.sub(r"\s+", "", str(s))


def rows_from_boxes(boxes, tol=16):
    """boxes: list(text,cx,cy). 按 cy 聚类成行, 返回 list[list[(text,cx,cy)]]."""
    boxes = sorted(boxes, key=lambda b: b[2])
    rows = []
    cur = []
    cur_y = None
    for b in boxes:
        _, _, cy = b
        if cur_y is None or abs(cy - cur_y) <= tol:
            cur.append(b)
            cur_y = cy if cur_y is None else (cur_y * (len(cur) - 1) + cy) / len(cur)
        else:
            rows.append(cur)
            cur = [b]
            cur_y = cy
    if cur:
        rows.append(cur)
    return rows


def process_year(ocr, year: int, x1: int):
    name = {2014: "nj2015_20-11", 2015: "nj2016_20-11",
            2016: "nj2017_20-10", 2017: "nj2018_20-10"}[year]
    img = cv2.imread(str(IMG / f"{name}.jpg"))
    strip = img[:, 0:x1]
    r = ocr.predict(strip)
    boxes = []   # (text,cx,cy)
    for page in r:
        for text, score, poly in zip(page.get("rec_texts", []), page.get("rec_scores", []), page.get("rec_polys", [])):
            poly = poly.astype(int)
            boxes.append((str(text), int(poly[:, 0].mean()), int(poly[:, 1].mean())))
    # 丢弃表头/标题(cy<200)
    boxes = [b for b in boxes if b[2] > 200]
    rows = rows_from_boxes(boxes)
    records = []
    cur_city = ""
    for row in rows:
        # 该行最左侧的汉字 == 县名/城市
        cjk = [b for b in row if re.search(r"[\u4e00-\u9fff]", b[0])]
        if not cjk:
            continue
        left = min(cjk, key=lambda b: b[1])   # cx 最小 = 县名列
        name = strip_ws(left[0])
        if name in PRECITY:
            cur_city = name
            continue
        # 播种面积数值: cx 在 [col2_left, x1) 的数字
        num = None
        for b in row:
            t = b[0]
            if re.search(r"\d", t) and b[1] >= 60:
                val = float(re.sub(r"[^\d.]", "", t)) if re.search(r"\d", t) else None
                if val is not None:
                    num = val
                    break
        if num is not None and name:
            records.append({"city": cur_city, "county": name, "grain_sown_ha": num})
    dst = OUT / f"{year}.csv"
    with open(dst, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["city", "county", "grain_sown_ha"])
        w.writeheader()
        w.writerows(records)
    print(f"data{year}: {len(records)} records -> {dst}", flush=True)


if __name__ == "__main__":
    CROP = {2014: 340, 2015: 340, 2016: 340, 2017: 405}
    years = [int(sys.argv[1])] + [int(a) for a in sys.argv[2:]]
    ocr = PaddleOCR(use_doc_orientation_classify=False,
                    use_doc_unwarping=False, use_textline_orientation=False, lang="ch")
    for y in years:
        process_year(ocr, y, CROP.get(y, 340))
