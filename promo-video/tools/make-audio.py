"""合成底噪音床与音效。

片子里没有可用的授权音乐素材，所以底噪用正弦堆叠手搓：
  - underscore.wav : 20s 环境铺底，A 小调开放和弦，2s 起音，末段轻微抬升
  - sfx-tick.wav   : 数据落位音，短促、干净、不刺耳
  - sfx-whoosh.wav : 转场气声，带通噪声扫频

音量不在这里定，交给 index.html 的 data-volume 控制。
用法: python tools/make-audio.py
"""
from __future__ import annotations

import pathlib

import numpy as np
import soundfile as sf

ROOT = pathlib.Path(__file__).resolve().parent.parent
SR = 48000
DUR = 20.0
SEED = 20260916  # 固定种子：渲染要可复现


def norm(x: np.ndarray, peak: float = 1.0) -> np.ndarray:
    m = float(np.max(np.abs(x))) or 1.0
    return (x / m * peak).astype(np.float32)


# ── 底噪：A 小调开放和弦 ────────────────────────────────────────────────────
t = np.arange(int(DUR * SR)) / SR
pad = np.zeros_like(t)

# (频率, 振幅, 轻微失谐量) —— 失谐是为了让正弦不"电子"
VOICES = [
    (55.00, 0.30, 0.15),    # A1
    (110.00, 0.34, 0.22),   # A2
    (164.81, 0.24, 0.31),   # E3
    (220.00, 0.22, 0.40),   # A3
    (261.63, 0.14, 0.52),   # C4
    (329.63, 0.10, 0.61),   # E4
]

for freq, amp, detune in VOICES:
    for k, sign in ((0, 1), (1, -1)):
        f = freq * (1 + sign * detune * 0.001) + k * 0.11
        pad += amp * np.sin(2 * np.pi * f * t + freq)

# 两秒起音 + 缓慢呼吸 + 末段抬升（落版处让音乐稍微托一下）
attack = np.clip(t / 2.0, 0, 1) ** 1.6
breath = 0.85 + 0.15 * np.sin(2 * np.pi * t / 7.3 - 1.1)
swell = 1.0 + 0.28 * np.clip((t - 13.5) / 4.0, 0, 1)
release = np.clip((DUR - t) / 1.6, 0, 1) ** 1.2
pad *= attack * breath * swell * release

# 一层很低的"空气感"，让 pad 不至于太干
rng = np.random.default_rng(SEED)
air = rng.standard_normal(len(t)).astype(np.float64)
kernel = np.ones(180) / 180
air = np.convolve(air, kernel, mode="same")
air *= 0.045 * attack * release
air *= 0.6 + 0.4 * np.sin(2 * np.pi * t / 11.0)

underscore = norm(pad + air, 0.92)
sf.write(ROOT / "underscore.wav", underscore, SR)


# ── SFX：数据落位音 ─────────────────────────────────────────────────────────
def make_tick() -> np.ndarray:
    d = 0.16
    tt = np.arange(int(d * SR)) / SR
    body = np.sin(2 * np.pi * 1760 * tt) * np.exp(-tt * 42)
    sub = np.sin(2 * np.pi * 880 * tt) * np.exp(-tt * 30) * 0.4
    click = rng.standard_normal(len(tt)) * np.exp(-tt * 320) * 0.28
    return norm(body + sub + click, 0.95)


# ── SFX：转场气声（带通噪声扫频） ────────────────────────────────────────────
def make_whoosh() -> np.ndarray:
    d = 0.62
    tt = np.arange(int(d * SR)) / SR
    noise = rng.standard_normal(len(tt))

    # 一阶带通（双极点）中心频率从 260Hz 扫到 1500Hz 再落回 420Hz
    sweep = 260 + 1240 * np.sin(np.pi * np.clip(tt / d, 0, 1)) ** 1.4
    out = np.zeros_like(noise)
    lp = 0.0
    bp = 0.0
    for i in range(len(noise)):
        f = 2 * np.sin(np.pi * sweep[i] / SR)
        lp += f * (noise[i] - lp)
        hp = noise[i] - lp
        bp += f * (hp - bp)
        out[i] = bp

    env = np.sin(np.pi * np.clip(tt / d, 0, 1)) ** 1.8
    return norm(out * env, 0.9)


sf.write(ROOT / "sfx-tick.wav", make_tick(), SR)
sf.write(ROOT / "sfx-whoosh.wav", make_whoosh(), SR)

print("wrote underscore.wav (20s), sfx-tick.wav, sfx-whoosh.wav @ 48k")
