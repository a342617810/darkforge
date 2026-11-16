# -*- coding: utf-8 -*-
"""战灰「唤声船」骑船的声音（用户 2026-11-11「唤声船和雷电羊球的音效呢」→ 按方案做）：唤声者的摇铃、船声都在它自己的音效库 cs_c4950，
只有唤声者在附近时才载入，玩家平时放不出来 → 自己合成，dark_core 的 sound.rs 用 Windows 的 PlaySound 放（boat.rs 上船 / 下船时）。
  boat_start.wav  上船：手铃响两下（钟的非谐波分音 0.5 / 1 / 1.19 / 1.5 / 2 / 2.51 / 3.01 / 4.17，各自衰减，叠一点失谐出拍频）+ 回响，
                  1 秒后幽灵嗡鸣渐入，结尾和循环的开头接得上
  boat_loop.wav   骑行中循环（6 秒，首尾无缝：所有频率都是 1/6 Hz 的整数倍，噪声用频域滤波 = 循环卷积）：
                  低沉嗡鸣（73.5 Hz 根音 + 五度 + 八度，慢慢颤动）、随呼吸起伏的气声（带通噪声）、几下水拍船身（低通噪声的短包络）、很淡的高音微光
输出到本目录，用的复制到 dll\\dark_core\\sounds\\。用法：python make_boat.py（要 numpy）"""
import os
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SR = 44100
LOOP = 6.0
N = int(SR * LOOP)
t = np.arange(N) / SR
rng = np.random.default_rng(11)


def q(f):
    """频率取整到 1/6 Hz 的倍数（6 秒循环里正好整数个周期）"""
    return round(f * LOOP) / LOOP


def band_noise(lo, hi, n=N, seed=0):
    """频域带通的白噪声（循环的：首尾自然接上）"""
    r = np.random.default_rng(seed)
    X = np.fft.rfft(r.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / SR)
    w = np.clip((f - lo * 0.7) / (lo * 0.3 + 1e-9), 0, 1) * np.clip((hi * 1.3 - f) / (hi * 0.3), 0, 1)
    x = np.fft.irfft(X * w, n)
    return x / (np.max(np.abs(x)) + 1e-9)


def drone():
    """幽灵嗡鸣：根音 / 五度 / 八度 + 微失谐的副本，振幅慢慢颤（周期 3 秒、2 秒）"""
    out = np.zeros(N)
    for f, a in ((73.5, 1.0), (110.25, 0.55), (147.0, 0.45), (220.5, 0.18)):
        f = q(f)
        df = 1.0 / LOOP                                   # 失谐 1/6 Hz：6 秒一次拍
        trem = 0.75 + 0.25 * np.sin(2 * np.pi * t / 3.0 + f)
        out += a * trem * (np.sin(2 * np.pi * f * t) + 0.7 * np.sin(2 * np.pi * (f + df) * t + 1.3))
    return out / np.max(np.abs(out))


def breath():
    """气声：300~1200 Hz 的带通噪声，随 3 秒的「呼吸」起伏"""
    env = 0.35 + 0.65 * (0.5 - 0.5 * np.cos(2 * np.pi * t / 3.0)) ** 1.5
    return band_noise(300, 1200, seed=3) * env


def water():
    """水拍船身：几下低通噪声的短包络（位置固定，循环里不会断在半截）"""
    out = np.zeros(N)
    base = band_noise(80, 700, seed=5)
    for at, a, d in ((0.35, 1.0, 0.35), (1.9, 0.7, 0.28), (3.3, 0.9, 0.4), (4.75, 0.6, 0.3)):
        i = int(at * SR)
        k = np.arange(N - i) / SR
        env = np.where(k < 0.04, k / 0.04, np.exp(-(k - 0.04) / d))
        out[i:] += a * env * base[: N - i]
    return out / (np.max(np.abs(out)) + 1e-9)


def shimmer():
    """很淡的高音微光：两个高音正弦，慢慢明暗（周期 6 秒）"""
    env = 0.5 - 0.5 * np.cos(2 * np.pi * t / LOOP)
    return env * (np.sin(2 * np.pi * q(1174.0) * t) + 0.6 * np.sin(2 * np.pi * q(1760.5) * t + 0.7)) / 1.6


def loop_mix():
    x = 0.55 * drone() + 0.22 * breath() + 0.3 * water() + 0.05 * shimmer()
    return x / np.max(np.abs(x))


def bell(f0, dur, seed):
    """手铃一下：钟的分音（hum / prime / tierce / quint / nominal / 高次）"""
    r = np.random.default_rng(seed)
    n = int(SR * dur)
    k = np.arange(n) / SR
    out = np.zeros(n)
    for ratio, a, tau in ((0.5, 0.35, 1.6), (1.0, 1.0, 1.2), (1.19, 0.5, 0.9), (1.5, 0.35, 0.8), (2.0, 0.6, 0.7),
                          (2.51, 0.3, 0.45), (3.01, 0.22, 0.35), (4.17, 0.12, 0.22)):
        f = f0 * ratio
        ph = r.uniform(0, 2 * np.pi)
        out += a * np.exp(-k / tau) * (np.sin(2 * np.pi * f * k + ph) + 0.4 * np.sin(2 * np.pi * f * 1.002 * k + ph))
    click = r.standard_normal(int(SR * 0.003)) * np.linspace(1, 0, int(SR * 0.003))
    out[: len(click)] += 0.3 * click
    a = int(SR * 0.001)
    out[:a] *= np.linspace(0, 1, a)
    return out


def reverb(x, rt=1.2, mix=0.35, seed=7):
    r = np.random.default_rng(seed)
    n = int(SR * rt)
    ir = r.standard_normal(n) * np.exp(-np.arange(n) / (SR * rt / 6.9))
    ir[: int(SR * 0.02)] = 0
    ir /= np.sqrt(np.sum(ir ** 2))
    wet = np.convolve(x, ir)
    out = np.zeros(len(wet))
    out[: len(x)] += x
    return out + mix * wet / (np.max(np.abs(wet)) + 1e-9) * np.max(np.abs(x))


def start_mix(loop):
    """上船：0 秒、0.55 秒各一下铃（第二下轻一点、高一点点），回响；1 秒起嗡鸣（循环本身）渐入，3 秒到循环的音量。
    长度 = 3 秒，结尾正好是循环第 0 秒前那一刻，接着放循环就连上了"""
    L = int(SR * 3.0)
    b = np.zeros(int(SR * 2.6))
    b1 = bell(784.0, 2.4, 1)
    b2 = bell(784.0 * 1.003, 2.0, 2)
    b[: len(b1)] += b1
    o = int(SR * 0.55)
    b[o: o + len(b2)] += 0.7 * b2[: len(b) - o]
    b = reverb(b)[:L] if len(reverb(b)) >= L else np.pad(reverb(b), (0, L - len(reverb(b))))
    b = b / np.max(np.abs(b))
    # 循环的最后 3 秒当作「之前」的那段，渐入
    tail = loop[N - L:]
    fade = np.clip((np.arange(L) / SR - 1.0) / 2.0, 0, 1)
    return 0.8 * b, fade * tail


def write(name, x, peak):
    x = x / (np.max(np.abs(x)) + 1e-9) * peak
    p = os.path.join(HERE, name)
    with wave.open(p, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype('<i2').tobytes())
    print('写好', name, '%.2f 秒' % (len(x) / SR))


def main():
    loop = loop_mix()
    LOOP_PEAK = 0.28                                       # 骑行中是背景声，压低
    write('boat_loop.wav', loop, LOOP_PEAK)
    bell_part, drone_in = start_mix(loop)
    # 嗡鸣那部分按循环的音量，铃按 0.45 的峰值叠上去
    s = drone_in * LOOP_PEAK + bell_part * (0.45 / 0.8) * 0.8
    with wave.open(os.path.join(HERE, 'boat_start.wav'), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(s, -1, 1) * 32767).astype('<i2').tobytes())
    print('写好 boat_start.wav %.2f 秒' % (len(s) / SR))
    # 试听用：上船 + 循环两遍
    write('boat_preview.wav', np.concatenate([s, loop * LOOP_PEAK, loop * LOOP_PEAK]), 0.45)


if __name__ == '__main__':
    main()
