"""把 4 句 VO 拼成 20 秒母带，并写出 beat 时间轴。

做三件事：
1. 裁掉每句首尾的静音（Kokoro 句首尾留白较长，不裁节奏会发飘）
2. 按 beat 规划拼接 narration.wav，整片正好 20.0s
3. 输出 transcript.json（句级时间戳）与 beat-timing.json（镜头时间轴）

用法: python tools/make-narration.py
"""
from __future__ import annotations

import json
import pathlib

import numpy as np
import soundfile as sf

ROOT = pathlib.Path(__file__).resolve().parent.parent
VO_DIR = ROOT / "vo"
TOTAL = 20.0
HEAD = 0.30          # 第一句入声前的留白
GAP = 0.90           # 句间呼吸
TAIL_MIN = 1.00      # 末句之后至少留这么多
THRESH = 0.10        # 静音判定阈值（相对 RMS 峰值）

LINES = [
    "极端气候，正在重写中国粮食的风险地图。",
    "稷韧云图，四类数据源，三模型互补归因。",
    "因子归因到省，情景模拟两秒出结果。",
    "让 AI，看见每一粒粮食的气候风险。",
]

SR = 24000


def trim_silence(x: np.ndarray, thresh: float = THRESH) -> np.ndarray:
    """裁掉首尾静音。

    不能用逐样本幅度判定：TTS 尾部有很长的低电平衰减，会误判成"还在说话"。
    改用时窗 RMS 包络，阈值取包络峰值的 10%，两端各留 80ms 余量保住起音与尾音。
    """
    win = max(1, int(0.05 * SR))
    kernel = np.ones(win, dtype=np.float32) / win
    rms = np.sqrt(np.convolve(x.astype(np.float64) ** 2, kernel, mode="same"))
    peak = float(rms.max()) or 1.0
    loud = np.where(rms > peak * thresh)[0]
    if len(loud) == 0:
        return x
    pad = int(0.08 * SR)
    start = max(0, int(loud[0]) - pad)
    end = min(len(x), int(loud[-1]) + pad)
    return x[start:end]


clips = []
for i in range(1, len(LINES) + 1):
    data, file_sr = sf.read(VO_DIR / f"line-{i}.wav", dtype="float32")
    SR = file_sr
    if data.ndim > 1:
        data = data.mean(axis=1)
    raw_dur = len(data) / SR
    trimmed = trim_silence(data)
    clips.append(trimmed)
    print(f"line-{i}: raw {raw_dur:5.2f}s -> trimmed {len(trimmed) / SR:5.2f}s  {LINES[i - 1]}")

# 先按固定 head/gap 排一遍，多出来的时间全部补给末尾留白
positions = []
cursor = HEAD
for clip in clips:
    positions.append(cursor)
    cursor += len(clip) / SR + GAP
cursor -= GAP

tail = TOTAL - cursor
if tail < TAIL_MIN:
    raise SystemExit(
        f"总时长不够：末句结束在 {cursor:.2f}s，只剩 {tail:.2f}s 尾部留白（需要 >= {TAIL_MIN}s）。"
        "把 -s 语速调高或删字。"
    )

total_samples = int(round(TOTAL * SR))
bus = np.zeros(total_samples, dtype=np.float32)
for clip, pos in zip(clips, positions):
    start = int(round(pos * SR))
    bus[start : start + len(clip)] += clip

# 统一峰值 0.89（约 -1.0 dBFS）
peak = float(np.max(np.abs(bus)))
if peak > 0:
    bus *= 0.89 / peak

sf.write(ROOT / "narration.wav", bus, SR)

(ROOT / "narration.txt").write_text("\n".join(LINES) + "\n", encoding="utf-8")

transcript = []
beats = []
for i, (text, clip, pos) in enumerate(zip(LINES, clips, positions), start=1):
    end = pos + len(clip) / SR
    transcript.append({"text": text, "start": round(pos, 3), "end": round(end, 3)})
    next_start = positions[i] if i < len(positions) else None
    beats.append(
        {
            "beat": i,
            "start": round(pos, 3),
            "vo_end": round(end, 3),
            "end": round(next_start, 3) if next_start is not None else TOTAL,
            "duration": round((next_start if next_start is not None else TOTAL) - pos, 3),
            "vo": text,
        }
    )

(ROOT / "transcript.json").write_text(json.dumps(transcript, ensure_ascii=False, indent=2), encoding="utf-8")
(ROOT / "beat-timing.json").write_text(json.dumps(beats, ensure_ascii=False, indent=2), encoding="utf-8")

print(f"\nnarration.wav  {TOTAL:.2f}s  ({total_samples} samples @ {SR} Hz)")
print(f"tail {tail:.2f}s | peak normalized to 0.89")
for b in beats:
    print(f"  beat {b['beat']}: {b['start']:5.2f} -> {b['end']:5.2f}  ({b['duration']:.2f}s)  vo ends {b['vo_end']:.2f}s")
