"""
8a — Train/test split (8:2 temporal)
Matches #6 split strategy: last 20% years = test
"""
import pandas as pd
from pathlib import Path

PROJ = Path('/home/slz/workspace/DC-AIino')
v4 = pd.read_parquet(PROJ / 'data/interim/paper_panel_v4.parquet')

# Sort by year
v4 = v4.sort_values(['province', 'year'])

# 8:2 temporal split (last 20% years)
years = sorted(v4['year'].unique())
split_idx = int(len(years) * 0.8)
train_years = years[:split_idx]
test_years = years[split_idx:]

print(f"Years: {years}")
print(f"Train years ({len(train_years)}): {train_years}")
print(f"Test years  ({len(test_years)}): {test_years}")

train = v4[v4['year'].isin(train_years)]
test = v4[v4['year'].isin(test_years)]

print(f"\nTrain: {train.shape} ({len(train)/len(v4)*100:.1f}%)")
print(f"Test:  {test.shape} ({len(test)/len(v4)*100:.1f}%)")

# Save
train.to_csv(PROJ / 'data/interim/train_v4.csv', index=False)
test.to_csv(PROJ / 'data/interim/test_v4.csv', index=False)

# Also save parquet versions
train.to_parquet(PROJ / 'data/interim/train_v4.parquet', index=False)
test.to_parquet(PROJ / 'data/interim/test_v4.parquet', index=False)

print(f"\nSaved: train_v4.csv, test_v4.csv (+ parquet)")
print(f"Files:")
for f in ['train_v4.csv', 'test_v4.csv', 'train_v4.parquet', 'test_v4.parquet']:
    p = PROJ / 'data/interim' / f
    if p.exists():
        print(f"  {p} ({p.stat().st_size:,} bytes)")

# Verify no data leakage
train_provs = set(train['province'])
test_provs = set(test['province'])
print(f"\nProvince overlap (expected all 31): {len(train_provs & test_provs)}")
print(f"Year overlap (should be 0): {set(train['year']) & set(test['year'])}")
