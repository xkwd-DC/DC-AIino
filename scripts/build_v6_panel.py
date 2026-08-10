# -*- coding: utf-8 -*-
"""Build v6 county-level panel from yearbook panel A + B (lon/lat).
Window: 10 grain provinces x 2012-2023. Outputs parquet raw + filled(linear-interp).
Run: python scripts/build_v6_panel.py
"""
import os, math, pandas as pd

BASE = r'D:\DC\DC-AIino\data\raw\statistical_yearbook\【25170】中国县域统计年鉴2000-2024'
A = BASE + r'\区县面板数据2000-2024.xlsx'
B = BASE + r'\中国县域统计年鉴（县市卷）【2000-2023】\02.面板数据\【出版年份2001-2023】中国县域面板数据.xlsx'
OUT = r'D:\DC\DC-AIino\data\interim'
TEN = ['河北省','吉林省','黑龙江省','江苏省','安徽省','山东省','河南省','湖北省','湖南省','四川省']
YEARS = list(range(2012, 2024))

# Y + agri-stat features from panel A
Y = '粮食总产量_吨'
STAT_COLS = [
    '农作物总播种面积_千公顷', '常用耕地面积_公顷', '机收面积_公顷', '设施农业占地面积_公顷',
    '农用机械总动力_千万瓦', '农林牧渔业总产值_万元', '农业增加值_万元', '第一产业增加值_万元',
    '乡村人口_万人', '乡村从业人员数_人', '农林牧渔业从业人员数_人',
]
ID_COLS = ['区县代码', '省份', '城市', '区县', '年份']

def build(sheet):
    df = pd.read_excel(A, sheet_name=sheet)
    df = df[df['省份'].isin(TEN) & df['年份'].isin(YEARS)]
    df = df[ID_COLS + [Y] + STAT_COLS].copy()
    logy = pd.to_numeric(df[Y], errors='coerce')
    df['log_yield'] = logy.where(logy > 0).map(lambda v: pd.NA if pd.isna(v) else math.log(v))
    return df

def attach_lonlat(df):
    b = pd.read_excel(B, sheet_name='原始数据', usecols=['行政区划代码', '经度', '纬度'])
    b = b.drop_duplicates('行政区划代码')
    return df.merge(b.rename(columns={'行政区划代码': '区县代码', '经度': 'lon', '纬度': 'lat'}),
                    on='区县代码', how='left')

def report(df, tag):
    print(f'[{tag}] {df.shape}  (10省 {df["区县代码"].nunique()} 县 x {df["年份"].nunique()} 年)')
    print(f'  分年县数: {df.groupby("年份")["区县代码"].nunique().to_dict()}')
    print(f'  粮食总产量非空率: {df["粮食总产量_吨"].notna().mean():.1%}  log_yield非空率: {df["log_yield"].notna().mean():.1%}')
    print(f'  经纬度非空率: {df["lon"].notna().mean():.1%}')
    for c in STAT_COLS:
        print(f'  {c}: 非空 {df[c].notna().mean():.1%}')
    out = os.path.join(OUT, 'paper_panel_v6.parquet' if tag == 'raw' else 'paper_panel_v6_filled.parquet')
    df.to_parquet(out, index=False)
    print(f'  saved -> {os.path.basename(out)}\n')

print('=== building raw ===')
raw = build('原始数据')
raw = attach_lonlat(raw)
report(raw, 'raw')

print('=== building filled (linear interp sheet) ===')
filled = build('线性插值')
filled = attach_lonlat(filled)
report(filled, 'filled')
