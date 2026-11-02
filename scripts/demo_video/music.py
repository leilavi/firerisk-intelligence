"""Original background music, synthesised in code (no samples, no third-party audio).
~108 BPM. Scene 1 (0..t1): dark, tense minor pad + heartbeat pulse. From t1: brighter major progression with soft bass,
light kick and hats. Ends with a resolved chord. Usage: python music.py total_seconds t1 out.wav"""
import sys
import numpy as np
import soundfile as sf
from scipy.signal import butter, lfilter

SR = 48000
total, t1, out = float(sys.argv[1]), float(sys.argv[2]), sys.argv[3]
N = int(total * SR)
mix = np.zeros((N, 2))
BPM = 108
beat = 60 / BPM
rng = np.random.default_rng(7)


def note(f, dur, kind="pad", amp=0.1):
    n = int(dur * SR); t = np.arange(n) / SR
    if kind == "pad":
        w = sum(np.sin(2 * np.pi * f * d * t + ph) for d, ph in ((1, 0), (1.003, 1.1), (0.997, 2.3), (2.001, 0.4)))
        w = w / 4 + 0.15 * np.sin(2 * np.pi * f * 0.5 * t)
        a = np.minimum(1, t / 0.8) * np.minimum(1, (dur - t) / 0.9)
    elif kind == "bass":
        w = np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * 2 * f * t)
        a = np.minimum(1, t / 0.02) * np.exp(-t * 1.6)
    elif kind == "pluck":
        w = np.sin(2 * np.pi * f * t) + 0.4 * np.sin(2 * np.pi * 2 * f * t) + 0.15 * np.sin(2 * np.pi * 3 * f * t)
        a = np.minimum(1, t / 0.005) * np.exp(-t * 5)
    return w * a * amp


def add(sig, start, pan=0.0):
    i = int(start * SR)
    if i >= N:
        return
    sig = sig[: N - i]
    mix[i:i + len(sig), 0] += sig * (1 - pan) / 1.0
    mix[i:i + len(sig), 1] += sig * (1 + pan) / 1.0


def lp(x, fc):
    b, a = butter(2, fc / (SR / 2))
    return lfilter(b, a, x)


def kick(amp=0.5):
    n = int(0.35 * SR); t = np.arange(n) / SR
    f = 110 * np.exp(-t * 18) + 42
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9) * amp


def hat(amp=0.05):
    n = int(0.06 * SR); t = np.arange(n) / SR
    x = rng.standard_normal(n)
    x = x - lp(x, 7000)
    return x * np.exp(-t * 60) * amp


def heart(amp=0.35):
    n = int(0.25 * SR); t = np.arange(n) / SR
    return np.sin(2 * np.pi * 55 * t) * np.exp(-t * 14) * amp


m = lambda k: 440 * 2 ** ((k - 69) / 12)
# --- scene 1: A minor drone, tension
bar = 4 * beat
t = 0.0
minor = [[57, 60, 64], [53, 57, 60], [55, 59, 62], [52, 56, 59]]     # Am F G E
k = 0
while t < t1 - 0.2:
    ch = minor[k % 4]
    for nn in ch:
        add(lp(note(m(nn - 12), bar + 0.9, "pad", 0.07), 1200), t, pan=rng.uniform(-.3, .3))
    for b in range(4):
        if t + b * beat < t1 - 0.3:
            add(heart(), t + b * beat); add(heart(0.18), t + b * beat + 0.18)
    t += bar; k += 1
# --- scenes 2-8: bright major, C G Am F with pluck arpeggio
prog = [[60, 64, 67], [55, 59, 62, 67], [57, 60, 64], [53, 57, 60, 65]]
t = t1
k = 0
end = total - 3.0
while t < end:
    ch = prog[k % 4]
    for nn in ch:
        add(lp(note(m(nn), bar + 0.8, "pad", 0.05), 2200), t, pan=rng.uniform(-.4, .4))
    add(note(m(ch[0] - 24), bar, "bass", 0.16), t)
    add(note(m(ch[0] - 24), beat * 1.5, "bass", 0.10), t + 2.5 * beat)
    arp = ch + [ch[0] + 12]
    for s in range(8):
        add(note(m(arp[s % len(arp)] + 12), 0.5, "pluck", 0.045), t + s * beat / 2, pan=0.3 if s % 2 else -0.3)
    for b in range(4):
        add(kick(0.32 if b % 2 == 0 else 0.22), t + b * beat)
        add(hat(), t + b * beat + beat / 2, pan=0.2)
    t += bar; k += 1
# final resolved chord
for nn in [60, 64, 67, 72]:
    add(lp(note(m(nn), 3.4, "pad", 0.07), 2400), end)
add(note(m(36), 3.0, "bass", 0.14), end)
mix = mix / (np.max(np.abs(mix)) + 1e-9) * 0.8
fade = np.ones(N); fl = int(1.2 * SR); fade[-fl:] = np.linspace(1, 0, fl)
mix *= fade[:, None]
sf.write(out, mix, SR)
print("music", total, "s")
