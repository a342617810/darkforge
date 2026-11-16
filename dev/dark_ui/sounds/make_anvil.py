# -*- coding: utf-8 -*-
"""装备工坊成功时的铁砧敲击声（用户 2026-11-10「都不太好 能自己做或者搜索铁砧敲击的声音吗」：游戏里 f 50000~50700 九个菜单音效都不像）。
自己合成，没有授权问题：钢块的非谐波振动（自由-自由梁的模态比 1 : 2.756 : 5.404 : 8.933 : 13.34，高的衰减快，每个模态再叠一个
微失谐的副本出「嗡」的拍频）+ 锤头击打的瞬态（几毫秒带通噪声 + 咔哒）+ 一点低频闷响 + 很淡的房间混响。
输出 44.1 kHz 16 位单声道 WAV：
  anvil_a.wav 清脆单击 / anvil_b.wav 厚重单击 / anvil_c.wav 叮叮两下（锤子弹一下，第二下轻）
用的那个复制成 dll\\dark_ui\\anvil.wav（dark_ui 在继承 / 重铸 / 超限成功时用 Windows 的 PlaySound 放，见 dark_ui 的 sound.rs）。
用法：python make_anvil.py（要 numpy）"""
import os
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SR = 44100
RATIOS = (1.0, 2.756, 5.404, 8.933, 13.34)


def strike(f0, dur, tau0, amps, thump, bright, seed):
    """一下敲击：模态求和 + 瞬态 + 闷响"""
    rng = np.random.default_rng(seed)
    t = np.arange(int(SR * dur)) / SR
    out = np.zeros_like(t)
    for k, (r, a) in enumerate(zip(RATIOS, amps)):
        f = f0 * r
        if f > SR * 0.45:
            continue
        tau = tau0 / r ** 0.75
        ph = rng.uniform(0, 2 * np.pi)
        det = 1.0 + rng.uniform(0.0015, 0.004)          # 拍频：两个几乎一样的模态
        env = np.exp(-t / tau)
        out += a * env * (np.sin(2 * np.pi * f * t + ph) + 0.55 * np.sin(2 * np.pi * f * det * t + ph * 1.7))
    # 锤头击打：3~6 ms 的带通噪声（亮度随 bright）+ 一个咔哒
    n = int(SR * 0.006)
    noise = rng.standard_normal(n) * np.exp(-np.arange(n) / (SR * 0.0015))
    # 粗糙的高通：一阶差分几次
    for _ in range(int(bright)):
        noise = np.diff(noise, prepend=0.0)
    noise /= np.max(np.abs(noise)) + 1e-9
    out[:n] += 0.9 * noise
    out[:int(SR * 0.0008)] += np.linspace(1.0, 0.0, int(SR * 0.0008)) * 0.8
    # 低频闷响（砧身）
    out += thump * np.sin(2 * np.pi * 150 * t) * np.exp(-t / 0.05)
    out += thump * 0.5 * np.sin(2 * np.pi * 95 * t) * np.exp(-t / 0.08)
    # 起振：前 0.5 ms 渐入，免得爆音
    a = int(SR * 0.0005)
    out[:a] *= np.linspace(0, 1, a)
    return out


def room(x, seed, mix=0.12, rt=0.45):
    """很淡的房间混响：和指数衰减的噪声做卷积"""
    rng = np.random.default_rng(seed)
    n = int(SR * rt * 1.5)
    ir = rng.standard_normal(n) * np.exp(-np.arange(n) / (SR * rt / 6.9))
    ir[: int(SR * 0.012)] = 0.0                        # 先到的直达声之后才有反射
    ir /= np.sqrt(np.sum(ir ** 2))
    wet = np.convolve(x, ir)[: len(x)]
    return x + mix * wet / (np.max(np.abs(wet)) + 1e-9) * np.max(np.abs(x))


def finish(x, peak=0.5):
    # 尾巴最后 80 ms 淡出
    f = int(SR * 0.08)
    x[-f:] *= np.linspace(1, 0, f)
    return x / (np.max(np.abs(x)) + 1e-9) * peak


def write(name, x):
    p = os.path.join(HERE, name)
    with wave.open(p, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype('<i2').tobytes())
    print('写好', p, '%.2f 秒' % (len(x) / SR))


def main():
    dur = 2.2
    a = strike(1180, dur, 1.25, (1.0, 0.55, 0.32, 0.18, 0.09), thump=0.25, bright=2, seed=1)
    write('anvil_a.wav', finish(room(a, 11)))
    b = strike(760, dur, 1.6, (1.0, 0.7, 0.35, 0.16, 0.07), thump=0.6, bright=1, seed=2)
    write('anvil_b.wav', finish(room(b, 12)))
    c1 = strike(1050, dur, 1.15, (1.0, 0.6, 0.3, 0.15, 0.08), thump=0.35, bright=2, seed=3)
    c2 = strike(1050 * 1.003, dur, 1.1, (1.0, 0.6, 0.3, 0.15, 0.08), thump=0.2, bright=2, seed=4)
    off = int(SR * 0.27)
    c = c1.copy()
    c1_tail = np.exp(-np.arange(len(c) - off) / (SR * 0.02))   # 第二下砸上去时第一下的余音被按住一部分
    c[off:] = c[off:] * (0.35 + 0.65 * c1_tail) + 0.55 * c2[: len(c) - off]
    write('anvil_c.wav', finish(room(c, 13)))


if __name__ == '__main__':
    main()
