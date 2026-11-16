# -*- coding: utf-8 -*-
"""装备工坊成功音效：厚重版（用户 2026-11-10「太清脆了啊 上网搜搜吧」→「有没有厚重一点的」→ 下载 Kenney 的 Impact Sounds）。
素材：kenney\\ 下是 Kenney「Impact Sounds」（CC0，www.kenney.nl，License.txt）里挑的几个，浏览器解码成 44.1 kHz 单声道 WAV。
挑法（频谱重心越低、400 Hz 以下能量越多越沉）：挖矿敲击 004 最沉（重心约 590 Hz、低频约 98%），钟形重击 001 余音最长（1.7 秒），
金属重击很短（0.1~0.4 秒，当「锤头砸下」那一下）。
输出 heavy_1~5.wav（峰值 0.5，尾巴淡出）：
  1 矿镐重击 / 2 矿镐重击 + 钟鸣余音 / 3 金属重击 + 低沉钟鸣（降调 10%）/ 4 金属板重击（降调 12%）/ 5 低沉钟鸣
用的那个复制成 dll\\dark_ui\\anvil.wav。用法：python make_heavy.py（要 numpy）"""
import os
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
K = os.path.join(HERE, 'kenney')
SR = 44100


def load(name):
    with wave.open(os.path.join(K, name + '.wav')) as w:
        assert w.getframerate() == SR and w.getnchannels() == 1
        return np.frombuffer(w.readframes(w.getnframes()), '<i2').astype(np.float64) / 32767.0


def pitch(x, factor):
    """降调（factor < 1 = 更低更长）：按比例重采样"""
    n = int(len(x) / factor)
    return np.interp(np.arange(n) * factor, np.arange(len(x)), x)


def mix(*parts):
    """(信号, 起点秒, 增益) 叠在一起"""
    n = max(int(at * SR) + len(x) for x, at, _g in parts)
    out = np.zeros(n)
    for x, at, g in parts:
        o = int(at * SR)
        out[o:o + len(x)] += g * x
    return out


def finish(x, peak=0.5, fade=0.06):
    f = min(len(x) // 4, int(SR * fade))
    x = x.copy()
    x[-f:] *= np.linspace(1, 0, f)
    return x / (np.max(np.abs(x)) + 1e-9) * peak


def write(name, x):
    p = os.path.join(HERE, name)
    with wave.open(p, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype('<i2').tobytes())
    print('写好', name, '%.2f 秒' % (len(x) / SR))


def bright(x, gain, fc=2000.0):
    """提亮：叠一份一阶高通（fc 以上）× gain"""
    a = 1.0 / (1.0 + 2 * np.pi * fc / SR)
    hp = np.zeros_like(x)
    for n in range(1, len(x)):
        hp[n] = a * (hp[n - 1] + x[n] - x[n - 1])
    return x + gain * hp


def main():
    write('heavy_1.wav', finish(load('impactMining_004')))
    # 用户 2026-11-10「1 可以稍微清亮一点」：1a 只提高频 / 1b 提高频 + 很轻的金属余音（钟形 002）/ 1c 升调 6% + 提高频
    m = load('impactMining_004')
    write('heavy_1a.wav', finish(bright(m, 1.2)))
    write('heavy_1b.wav', finish(bright(mix((m, 0, 1.0), (load('impactBell_heavy_002'), 0.004, 0.22)), 0.9)))
    write('heavy_1c.wav', finish(bright(pitch(m, 1.06), 0.8)))
    write('heavy_2.wav', finish(mix((load('impactMining_002'), 0, 1.0), (load('impactBell_heavy_002'), 0.005, 0.45))))
    write('heavy_3.wav', finish(pitch(mix((load('impactMetal_heavy_004'), 0, 1.0), (load('impactBell_heavy_001'), 0.004, 0.5)), 0.9)))
    write('heavy_4.wav', finish(pitch(load('impactPlate_heavy_004'), 0.88)))
    write('heavy_5.wav', finish(load('impactBell_heavy_001')))


if __name__ == '__main__':
    main()
