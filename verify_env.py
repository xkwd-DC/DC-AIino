"""一次性环境自检脚本——直接 python 跑就行，无需任何引号。"""
import sys

print(f"Python: {sys.version.split()[0]}")
print(f"路径:   {sys.executable}")
print()

libs = ["numpy", "pandas", "sklearn", "xgboost", "tensorflow", "shap", "matplotlib", "jupyter"]
ok = 0
for name in libs:
    try:
        m = __import__(name)
        v = getattr(m, "__version__", "?")
        print(f"  [OK]  {name:14s} {v}")
        ok += 1
    except Exception as e:
        print(f"  [X ]  {name:14s} {e}")

print()
print(f"{ok} / {len(libs)} 个库就绪。", "全部 OK，可以开始训练。" if ok == len(libs) else "有库缺失，请联系协作者。")
