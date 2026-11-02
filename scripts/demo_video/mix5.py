"""Voice-over (each scene at its start) + music bed (ducked under the voice) -> out/audio.wav, then mux with the video."""
import json, subprocess
import numpy as np
import soundfile as sf

D = "/home/claude/v5"
TIM = json.load(open(f"{D}/timing5.json"))
ORDER = ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8"]
SR = 48000
T, acc = {}, 0.0
for s in ORDER:
    T[s] = acc; acc += TIM["scenes"][s]
total = acc + 1.0
N = int(total * SR)
voice = np.zeros(N)
for s in ORDER:
    v, sr = sf.read(f"{D}/vo/{s}.wav")
    if v.ndim > 1:
        v = v.mean(1)
    assert sr == SR
    i = int((T[s] + TIM.get("vo_offsets", {}).get(s, TIM.get("vo_start", 0.15))) * SR)
    voice[i:i + len(v)] += v[: N - i]
music, sr = sf.read(f"{D}/music.wav")
music = music[:N] if len(music) >= N else np.pad(music, ((0, N - len(music)), (0, 0)))
# ducking envelope from voice energy
win = int(0.05 * SR)
env = np.sqrt(np.convolve(voice ** 2, np.ones(win) / win, mode="same"))
on = (env > 0.01).astype(float)
k = int(0.4 * SR)
on = np.convolve(on, np.ones(k) / k, mode="same").clip(0, 1)
gain = 0.30 - 0.18 * on            # music ~ -10 dB alone, ~ -18 dB under the voice
mix = music * gain[:, None] + voice[:, None] * 0.95
# --- light sound design (synthesised): electrical hum + relay clicks in scene 1, a soft chime at the citation check
rng = np.random.default_rng(3)
def put(sig, t0, g):
    i = int(t0 * SR)
    if 0 <= i < N:
        e = min(N, i + len(sig)); mix[i:e] += (sig[: e - i] * g)[:, None]
C = TIM["cues"]
tt = np.arange(int(SR * (TIM["scenes"]["s1"] - 0.6))) / SR
hum = (np.sin(2 * np.pi * 50 * tt) + 0.5 * np.sin(2 * np.pi * 100 * tt) + 0.2 * np.sin(2 * np.pi * 150 * tt))
hum *= np.minimum(1, tt / 1.5) * np.minimum(1, (tt[-1] - tt) / 1.5)
put(hum, 0.0, 0.018)
def click():
    n = int(0.03 * SR); x = rng.standard_normal(n) * np.exp(-np.arange(n) / SR * 260); return x
for k in ("water", "batt", "pa", "heat"):
    put(click(), T["s1"] + C["s1"][k] - 0.4, 0.10)
four = C["s1"]["four"] - 0.6
for i in range(4):
    put(click(), T["s1"] + four + i * 0.25, 0.07)
def chime(f=880):
    n = int(0.6 * SR); x = np.arange(n) / SR
    return (np.sin(2 * np.pi * f * x) + 0.4 * np.sin(2 * np.pi * 1.5 * f * x)) * np.exp(-x * 6)
put(chime(), T["s6"] + C["s6"]["cite"], 0.05)
peak = np.max(np.abs(mix))
if peak > 0.98:
    mix *= 0.98 / peak
sf.write(f"{D}/out/audio.wav", mix, SR)
subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", f"{D}/out/video_only.mp4", "-i", f"{D}/out/audio.wav",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-af", "loudnorm=I=-15:TP=-1.5", "-shortest",
                f"{D}/out/FireRisk_Intelligence_Demo_Final.mp4"], check=True)
print("muxed", total)
