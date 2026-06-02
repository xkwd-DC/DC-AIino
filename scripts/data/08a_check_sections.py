import pandas as pd
from pathlib import Path

BASE = Path('/home/slz/workspace/DC-AIino/data/raw/paper_panel/wang_tianshuo_original')

df_raw = pd.read_excel(BASE / '分省年度成灾数据 (5).xlsx', header=None)
print(f"Full shape: {df_raw.shape}")

# Print ALL rows - look for the second section
for i in range(len(df_raw)):
    cells = [str(df_raw.iloc[i, j])[:50] for j in range(min(6, df_raw.shape[1]))]
    print(f"Row {i:2d}: {cells}")
