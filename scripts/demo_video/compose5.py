"""Edit the demo video v3 from the real dashboard recording (demo mode) + voice-over + original music.
Inputs (dir rec/): capture.mp4, capture_info.json, marks.json; timing3.json, script.json, durs.json, vo/*.wav.
Output: out/FireRisk_demo_v3.mp4 (+ .srt). Zooms/spotlights follow marks.json (rectangles measured in the browser
during the take); scene 1 is drawn here from the four real records (text checked against the dashboard)."""
import json, math, subprocess, sys, textwrap
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

D = "/home/claude/v5"
REC = f"{D}/rec5"
OUT = f"{D}/out"
W, H, FPS = 1920, 1080, 30
TIM = json.load(open(f"{D}/timing5.json"))
VO0 = TIM.get("vo_start", 0.15)
SCRIPT = dict(json.load(open(f"{D}/script.json")))
DURS = json.load(open(f"{D}/durs.json"))
SC = TIM["scenes"]
ORDER = ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8"]
T = {}
acc = 0.0
for s in ORDER:
    T[s] = acc; acc += SC[s]
TAIL = 1.0
TOTAL = acc + TAIL
marks = json.load(open(f"{REC}/marks.json"))
info = json.load(open(f"{REC}/capture_info.json"))
first_t = info["first_frame_t"]
scene_c = {m["name"]: m["t"] for m in marks if m["type"] == "scene"}
end_c = next((m["t"] for m in marks if m["type"] == "end"), None)
cap_order = ORDER[1:]


def out_to_cap(t):
    """Output time -> capture time (seconds since t0 of the recorder)."""
    for i, s in enumerate(cap_order):
        nxt = T[cap_order[i + 1]] if i + 1 < len(cap_order) else TOTAL + 5
        if t < nxt or i == len(cap_order) - 1:
            cs = scene_c.get(s, 0)
            ce = scene_c.get(cap_order[i + 1]) if i + 1 < len(cap_order) else (end_c or cs + SC[s] + 2)
            ratio = (ce - cs) / SC[s] if s not in ("s8",) + tuple(TIM.get("trim_tail", [])) else 1.0
            return cs + (t - T[s]) * ratio
    return 0


def cap_to_out(c):
    for i, s in enumerate(cap_order):
        cs = scene_c.get(s, 0)
        ce = scene_c.get(cap_order[i + 1]) if i + 1 < len(cap_order) else 1e9
        if cs <= c < ce:
            ratio = (ce - cs) / SC[s] if s not in ("s8",) + tuple(TIM.get("trim_tail", [])) and ce < 1e9 else 1.0
            return T[s] + (c - cs) / ratio
    return T["s2"]


# ---------------- zoom track ----------------
zooms = [m for m in marks if m["type"] == "zoom"]
zooms = [dict(z, to=cap_to_out(z["t"])) for z in zooms]


def crop_for(z):
    if not z or not z.get("rect"):
        return (0.0, 0.0, float(W), float(H))
    x, y, w, h = z["rect"]
    sc = z.get("scale", 1.5)
    sc = max(1.0, min(sc, W * 0.86 / max(w, 1), H * 0.80 / max(h, 1), 2.4))
    cw, ch = W / sc, H / sc
    cx, cy = x + w / 2, y + h / 2
    x0 = min(max(0, cx - cw / 2), W - cw)
    y0 = min(max(0, cy - ch / 2), H - ch)
    return (x0, y0, cw, ch)


def ease(p):
    p = max(0.0, min(1.0, p))
    return p * p * (3 - 2 * p)


TR = 1.2


def view_at(t):
    """(crop box, spotlight rect in source px or None, spot alpha)."""
    prev, cur = None, None
    for z in zooms:
        if z["to"] <= t:
            prev, cur = cur, z
        else:
            break
    if cur is None:
        return (0, 0, W, H), None, 0
    a = crop_for(prev) if prev else (0, 0, W, H)
    b = crop_for(cur)
    p = ease((t - cur["to"]) / TR)
    box = tuple(a[i] + (b[i] - a[i]) * p for i in range(4))
    spot = cur["rect"] if cur.get("spot") and cur.get("rect") else None
    sa = ease((t - cur["to"] - 0.4) / 0.7) if spot else 0
    return box, spot, sa


# ---------------- fonts / drawing helpers ----------------
FB = "/usr/share/fonts/opentype/inter/Inter-Bold.otf"
FS = "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf"
FR = "/usr/share/fonts/opentype/inter/Inter-Regular.otf"
FM = "/usr/share/fonts/opentype/inter/Inter-Medium.otf"
font = lambda p, s: ImageFont.truetype(p, s)
CYAN = (34, 211, 238)
PINK = (244, 114, 182)
BG = (11, 18, 32)
STEPS = ["SOURCES", "RULES", "MUSE SPARK", "EVIDENCE", "AGENT", "VIDEO + SAM", "DECISION"]
SCENE_STEP = {"s2": 0, "s3": 1, "s4": 2, "s5": 3, "s6": 4, "s7": 5, "s8": 6}


def rrect(d, box, r, fill=None, outline=None, width=1):
    d.rounded_rectangle(box, r, fill=fill, outline=outline, width=width)


def journey(img, scene, t_in):
    if scene not in SCENE_STEP:
        return
    ov = Image.new("RGBA", (W, 56), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    rrect(d, (24, 8, W - 24, 50), 21, fill=(8, 13, 24, 205))
    f = font(FS, 17)
    k = SCENE_STEP[scene]
    allon = scene == "s8" and t_in > SC["s8"] - 5.2
    n = len(STEPS); x0, x1 = 48, W - 48
    cw = (x1 - x0) / n
    for i, s in enumerate(STEPS):
        cx = x0 + cw * (i + 0.5)
        on = i == k or allon
        done = i < k
        col = CYAN if on else ((150, 170, 190) if done else (90, 104, 124))
        tw = d.textlength(s, font=f)
        if on:
            rrect(d, (cx - tw / 2 - 16, 15, cx + tw / 2 + 16, 43), 14, fill=(34, 211, 238, 40), outline=CYAN, width=2)
        d.text((cx - tw / 2, 19), s, font=f, fill=col)
        if i < n - 1:
            ax = x0 + cw * (i + 1)
            d.text((ax - 6, 18), "›", font=f, fill=(70, 84, 104))
    img.alpha_composite(ov, (0, 0))


def label(img, text, alpha):
    if alpha <= 0:
        return
    f = font(FB, 30)
    d0 = ImageDraw.Draw(img)
    tw = d0.textlength(text, font=f)
    ov = Image.new("RGBA", (int(tw) + 60, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    rrect(d, (0, 0, tw + 58, 62), 14, fill=(8, 13, 24, 225), outline=CYAN, width=2)
    d.text((29, 13), text, font=f, fill=(240, 248, 255))
    ov.putalpha(ov.getchannel("A").point(lambda v: int(v * alpha)))
    img.alpha_composite(ov, (48, 84))


def subtitle(img, text):
    if not text:
        return
    f = font(FM, 34)
    lines = textwrap.wrap(text, 70)
    d0 = ImageDraw.Draw(img)
    lh = 46
    tw = max(d0.textlength(l, font=f) for l in lines)
    h = lh * len(lines) + 26
    ov = Image.new("RGBA", (int(tw) + 56, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    rrect(d, (0, 0, tw + 54, h - 1), 12, fill=(0, 0, 0, 170))
    for i, l in enumerate(lines):
        lw = d.textlength(l, font=f)
        d.text(((tw + 54 - lw) / 2, 12 + i * lh), l, font=f, fill=(255, 255, 255))
    img.alpha_composite(ov, (int((W - tw - 54) / 2), H - h - 34))


# ---------------- labels per scene (scene-relative seconds) ----------------
CU = TIM["cues"]
LABELS = {
    "s2": [(0.4, 6.0, "FireRisk Intelligence · Meta Global AI Developer Hackathon 2026 · Meta Muse Spark | SAM 3.1"),
           (CU["s2"]["connects"] - 0.5, SC["s2"] - 0.8, "Logs · meters · asset register · survey videos")],
    "s3": [(0.4, CU["s3"]["ats"] - 0.6, "RULE ENGINE · known relationships only"),
           (CU["s3"]["ats"] - 0.3, SC["s3"] - 0.5, "One ATS for all 6 floors · basis stated")],
    "s4": [(0.4, CU["s4"]["water"] - 0.4, "MUSE SPARK · investigates and explains"),
           (CU["s4"]["water"] - 0.2, CU["s4"]["grid"] + 0.8, "Water · 08 Oct · still unresolved"),
           (CU["s4"]["grid"] + 0.8, CU["s4"]["gen"] - 0.2, "Potential grid loss · not happened"),
           (CU["s4"]["gen"], CU["s4"]["lights"] - 0.2, "Starter batteries reported degraded · 29 Sep"),
           (CU["s4"]["lights"], CU["s4"]["battery"] - 0.3, "135 emergency lights & exit signs · 6 floors")],
    "s5": [(0.4, CU["s5"]["record"] - 1.2, "TRACEABLE EVIDENCE · every link states its basis"),
           (CU["s5"]["record"] - 1.2, CU["s5"]["unknown"] + 0.6, "SOURCE RECORD"),
           (CU["s5"]["unknown"] + 0.6, SC["s5"] - 0.3, "Equipment alert ↔ fire risk · unknown ≠ assumed")],
    "s6": [(0.4, CU["s6"]["cite"] - 0.3, "AGENTIC INVESTIGATION · read-only lookups"),
           (CU["s6"]["cite"] - 0.3, CU["s6"]["rules"] - 0.3, "CITATIONS VALIDATED"),
           (CU["s6"]["rules"] - 0.3, SC["s6"] - 0.3, "Rule-based risk level · AI unavailable? Rules still work")],
    "s7": [(0.4, 5.6, "MUSE SPARK ANALYZES · 14 survey videos"),
           (11.2, SC["s7"] - 0.3, "FIRERISK CONNECTS THE EVIDENCE · supporting, not proof")],
    "s8": [(0.4, CU["s8"]["decision"] - 0.3, "Recommended actions · not yet done"),
           (CU["s8"]["decision"] - 0.3, CU["s8"]["end"] - 0.6, "Decision support · a person confirms")],
}


def sub_items():
    """Subtitle timing: sentences spread over each scene's voice by character share (refined by transcript if any)."""
    items = []
    tr = None
    try:
        tr = json.load(open(f"{D}/sub_times.json"))
    except Exception:
        pass
    for s in ORDER:
        if tr and s in tr:
            for a, b, txt in tr[s]:
                items.append((T[s] + a, T[s] + b, txt))
            continue
        text = SCRIPT[s]
        import re
        parts = re.split(r"(?<=[.:])\s+", text)
        chunks = []
        for p in parts:
            if len(p) > 95:
                sub = re.split(r"(?<=,)\s+", p)
                buf = ""
                for q in sub:
                    if len(buf) + len(q) > 90 and buf:
                        chunks.append(buf.strip()); buf = q
                    else:
                        buf = (buf + " " + q).strip()
                if buf:
                    chunks.append(buf)
            else:
                chunks.append(p)
        dur = DURS[s] - 0.3
        tot = sum(len(c) + 8 for c in chunks)
        t = T[s] + TIM.get("vo_offsets", {}).get(s, VO0)
        for c in chunks:
            d_ = dur * (len(c) + 8) / tot
            items.append((t, t + d_ - 0.05, c)); t += d_
    return items


SUBS = sub_items()


def sub_at(t):
    for a, b, txt in SUBS:
        if a <= t < b:
            return txt
    return None


# ---------------- scene 1 (drawn) ----------------
CARDS = [
    ("08 Oct", "WATER IN ELECTRICAL ROOM", "Incident & works log", (56, 189, 248), "water"),
    ("29 Sep", "WEAK GENERATOR BATTERIES", "Asset repairs & maintenance", (250, 204, 21), "batt"),
    ("15 Sep", "ANNOUNCEMENT SYSTEM FAILURE", "Incident & works log", (244, 114, 182), "pa"),
    ("08 & 19 Oct", "FAULTY HEAT DETECTOR", "Incident & works log", (251, 146, 60), "heat"),
]
POS = [(170, 230), (1110, 230), (170, 640), (1110, 640)]
CW_, CH_ = 640, 190
C1S = CU["s1"]
try:
    S1_PHOTOS = json.load(open(f"{D}/s1_photos.json"))     # [[path, caption], ...] blurred survey frames, in cue order
except Exception:
    S1_PHOTOS = []
_photo_cache = {}


def photo(path):
    if path not in _photo_cache:
        im = Image.open(path).convert("RGB")
        r = max(W / im.width, H / im.height)
        _photo_cache[path] = im.resize((int(im.width * r) + 2, int(im.height * r) + 2), Image.LANCZOS)
    return _photo_cache[path]


def exit_icon(d, cx, cy, s, col):
    rrect(d, (cx - s, cy - s * 0.62, cx + s, cy + s * 0.62), 10, fill=(10, 60, 40), outline=col, width=3)
    f = font(FB, int(s * 0.45))
    tw = d.textlength("EXIT", font=f)
    d.text((cx - tw / 2, cy - s * 0.28), "EXIT", font=f, fill=col)


def scene1(t):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    d = ImageDraw.Draw(img)
    ph_start = C1S["water"] - 0.4
    cards_at = C1S["pa"] - 0.4 if len(S1_PHOTOS) == 2 else C1S["four"] - 0.6
    if t < ph_start:                                    # title on black
        a = min(ease(t / 0.8), ease((ph_start - t) / 0.4))
        f = font(FB, 64); txt = "A BUILDING DOESN'T FAIL ALL AT ONCE."
        tw = d.textlength(txt, font=f)
        d.text(((W - tw) / 2, H / 2 - 40), txt, font=f, fill=(int(240 * a), int(244 * a), int(250 * a)))
        return img
    if t < cards_at and S1_PHOTOS:                      # real blurred survey frames, slow push-in
        keys = ["water", "batt", "pa", "heat"]
        starts = [C1S[k] - 0.4 for k in keys[:len(S1_PHOTOS)]]
        k = max(i for i, st in enumerate(starts) if t >= st)
        end = starts[k + 1] if k + 1 < len(starts) else cards_at
        p = (t - starts[k]) / max(0.1, end - starts[k])
        im = photo(S1_PHOTOS[k][0])
        z = 1.0 + 0.08 * p
        cw, ch = W / z, H / z
        ox, oy = (im.width - cw) / 2, (im.height - ch) / 2
        fr = im.crop((int(ox), int(oy), int(ox + cw), int(oy + ch))).resize((W, H), Image.BILINEAR).convert("RGBA")
        fade = min(ease((t - starts[k]) / 0.35), 1.0)
        dim = Image.new("RGBA", (W, H), (0, 0, 0, int(255 * (1 - fade) + 60)))
        img.alpha_composite(fr); img.alpha_composite(dim)
        d = ImageDraw.Draw(img)
        lab = CARDS[k][1]
        f = font(FB, 46); tw = d.textlength(lab, font=f)
        rrect(d, (80, H - 230, 80 + tw + 60, H - 160), 14, fill=(8, 13, 24, 220), outline=CARDS[k][3], width=3)
        d.text((110, H - 222), lab, font=f, fill=(240, 248, 255))
        d.text((80, H - 140), "Building survey footage · blurred · " + S1_PHOTOS[k][1], font=font(FM, 22), fill=(200, 210, 222))
        return img
    img = Image.new("RGBA", (W, H), BG + (255,))
    d = ImageDraw.Draw(img)
    for x in range(0, W, 80):
        d.line((x, 0, x, H), fill=(18, 28, 46))
    for y in range(0, H, 80):
        d.line((0, y, W, y), fill=(18, 28, 46))
    centers = [(x + CW_ / 2, y + CH_ / 2) for x, y in POS]
    ex = (W / 2, H / 2 + 10)
    if t > C1S["same"]:                                 # each card -> the same EXIT (not to each other)
        for i, (cx, cy) in enumerate(centers):
            q = ease((t - C1S["same"] - i * 0.25) / 1.2)
            if q > 0:
                d.line((cx, cy, cx + (ex[0] - cx) * q, cy + (ex[1] - cy) * q), fill=CYAN, width=4)
    for i, (dt_, title, src, col, _) in enumerate(CARDS):
        appear = max(cards_at + i * 0.2, C1S[CARDS[i][4]] - 0.4)
        a = ease((t - appear) / 0.6)
        if a <= 0:
            continue
        x, y = POS[i]; y += (1 - a) * 30
        card = Image.new("RGBA", (CW_, CH_), (0, 0, 0, 0)); cd = ImageDraw.Draw(card)
        rrect(cd, (0, 0, CW_ - 1, CH_ - 1), 18, fill=(17, 26, 44, 245), outline=col, width=3)
        cd.text((30, 24), dt_, font=font(FB, 30), fill=col)
        cd.text((30, 76), title, font=font(FB, 31), fill=(236, 242, 250))
        cd.text((30, CH_ - 40), "SOURCE · " + src, font=font(FM, 20), fill=(148, 163, 184))
        card.putalpha(card.getchannel("A").point(lambda v: int(v * a)))
        img.alpha_composite(card, (int(x), int(y)))
    if t > C1S["same"] + 0.6:
        a = ease((t - C1S["same"] - 0.6) / 0.8)
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); od = ImageDraw.Draw(ov)
        exit_icon(od, ex[0], ex[1], 70, (74, 222, 128))
        od.text((ex[0] - 120, ex[1] + 60), "people evacuating", font=font(FM, 26), fill=(190, 242, 210))
        ov.putalpha(ov.getchannel("A").point(lambda v: int(v * a)))
        img.alpha_composite(ov)
    top = "Four records. Four logbooks." if t < C1S["bfly"] - 0.2 else "THE BUTTERFLY EFFECT"
    f = font(FB, 52); tw = d.textlength(top, font=f)
    d.text(((W - tw) / 2, 110), top, font=f, fill=CYAN if t >= C1S["bfly"] - 0.2 else (226, 232, 240))
    return img


# ---------------- SAM 3.1 frame sequence (scene 7) ----------------
try:
    SAM = json.load(open(f"{D}/sam_clip.json"))   # {"frames": [[path, [x0,y0,x1,y1] or null, "01:11"], ...], "phrase": .., "conf": ..}
except Exception:
    SAM = None
_sam_c = next((m["t"] for m in marks if m.get("name") == "sam_clip_start"), None)
_sam_e = next((m["t"] for m in marks if m.get("name") == "sam_clip_end"), None)


def sam_clip(u):
    """Real frame 01:11 where SAM 3.1 located the cable: slow push-in, then the box, then the mask outline (as returned)."""
    import re as _re
    path, box, tc = SAM["frames"][0]
    im = Image.open(path).convert("RGB")
    r = min(1820 / im.width, 1024 / im.height)
    im2 = im.resize((int(im.width * r), int(im.height * r)), Image.LANCZOS)
    bx = [v * r for v in box]
    z = 1.0 + 0.22 * ease(u)
    cx, cy = (bx[0] + bx[2]) / 2, (bx[1] + bx[3]) / 2
    cw, ch = im2.width / z, im2.height / z
    ox = min(max(0, cx - cw / 2), im2.width - cw); oy = min(max(0, cy - ch / 2), im2.height - ch)
    crop = im2.crop((int(ox), int(oy), int(ox + cw), int(oy + ch))).resize(im2.size, Image.LANCZOS).convert("RGBA")
    T_ = lambda x, y: ((x * r - ox) * z, (y * r - oy) * z)
    ba = ease((u - 0.2) / 0.15)
    if ba > 0:
        ov = Image.new("RGBA", crop.size, (0, 0, 0, 0)); od = ImageDraw.Draw(ov)
        if u > 0.45 and SAM.get("mask"):
            nums = list(map(float, _re.findall(r"-?\d+\.?\d*", SAM["mask"])))
            pts = [T_(box[0] + nums[k], box[1] + nums[k + 1]) for k in range(0, len(nums) - 1, 2)]
            ma = ease((u - 0.45) / 0.2)
            od.polygon(pts, fill=(34, 211, 238, int(70 * ma)), outline=(34, 211, 238, int(230 * ma)))
        b0, b1 = T_(box[0], box[1]), T_(box[2], box[3])
        od.rectangle([b0[0], b0[1], b1[0], b1[1]], outline=(34, 211, 238, int(255 * ba)), width=5)
        tag = f"SAM 3.1 · \"{SAM.get('phrase','')}\" · confidence {SAM.get('conf')}"
        f_ = font(FB, 28); tw = od.textlength(tag, font=f_)
        tx, ty = b0[0], max(8, b0[1] - 48)
        od.rounded_rectangle((tx - 6, ty - 4, tx + tw + 14, ty + 38), 8, fill=(8, 13, 24, int(220 * ba)))
        od.text((tx + 4, ty), tag, font=f_, fill=(34, 211, 238, int(255 * ba)))
        crop.alpha_composite(ov)
    canvas = Image.new("RGBA", (W, H), BG + (255,))
    canvas.alpha_composite(crop, ((W - crop.width) // 2, 56 + (1024 - crop.height) // 2))
    d = ImageDraw.Draw(canvas)
    d.text((70, 70), f"Meta SAM 3.1 · frame {tc} of the MSB room survey video · blurred copy · "
           f"located in 1 of 3 frames checked", font=font(FM, 24), fill=(220, 228, 238))
    return canvas


# ---------------- end card ----------------
END_START = T["s8"] + CU["s8"]["end"] - 0.4


def endcard(alpha):
    img = Image.new("RGBA", (W, H), BG + (255,))
    d = ImageDraw.Draw(img)
    f1, f2, f3 = font(FB, 92), font(FS, 40), font(FM, 26)
    for txt, f, y, col in (("FireRisk Intelligence", f1, 340, (240, 248, 255)),
                           ("MAKE HIDDEN RISK CONNECTIONS VISIBLE.", f2, 470, CYAN),
                           ("Because building risks rarely happen in isolation.", font(FM, 32), 530, (226, 232, 240)),
                           ("github.com/leilavi/firerisk-intelligence", f3, 600, (203, 213, 225)),
                           ("Built with Meta Muse Spark · SAM 3.1", f3, 650, (148, 163, 184)),
                           ("Decision support — not a replacement for certified fire safety systems", f3, 760, (148, 163, 184))):
        tw = d.textlength(txt, font=f)
        d.text(((W - tw) / 2, y), txt, font=f, fill=col)
    # butterfly-ish mark: chain of 5 linked dots
    for i in range(5):
        cx = W / 2 - 160 + i * 80
        d.ellipse((cx - 13, 240 - 13, cx + 13, 240 + 13), outline=CYAN, width=4)
        if i < 4:
            d.line((cx + 13, 240, cx + 67, 240), fill=CYAN, width=4)
    img.putalpha(int(255 * alpha))
    return img


# ---------------- main loop ----------------
def main():
    import os
    os.makedirs(OUT, exist_ok=True)
    nframes = int(TOTAL * FPS)
    cap = subprocess.Popen(["ffmpeg", "-v", "error", "-i", f"{REC}/capture.mp4", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                           stdout=subprocess.PIPE)
    enc = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                            "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p",
                            f"{OUT}/video_only.mp4"], stdin=subprocess.PIPE)
    cap_idx = -1
    cur = None
    fsz = W * H * 3

    def cap_frame(c):
        nonlocal cap_idx, cur
        want = max(0, int(round((c - first_t) * FPS)))
        while cap_idx < want:
            buf = cap.stdout.read(fsz)
            if len(buf) < fsz:
                break
            cur = buf; cap_idx += 1
        return Image.frombuffer("RGB", (W, H), cur)

    lim = int(sys.argv[1]) if len(sys.argv) > 1 else nframes
    for n in range(min(nframes, lim)):
        t = n / FPS
        scene = next(s for s in reversed(ORDER) if t >= T[s])
        tin = t - T[scene]
        if scene == "s1":
            img = scene1(tin)
            if tin > SC["s1"] - 0.6:              # cross-fade into the dashboard
                a = ease((tin - (SC["s1"] - 0.6)) / 0.6)
                src = cap_frame(out_to_cap(T["s2"])).convert("RGBA")
                img = Image.blend(img, src, a)
        else:
            c = out_to_cap(t)
            src = cap_frame(c)
            box, spot, sa = view_at(t)
            x0, y0, cw, ch = box
            fr = src.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch))).resize((W, H), Image.LANCZOS if cw < W - 1 else Image.NEAREST)
            img = fr.convert("RGBA")
            if spot and sa > 0:
                sx, sy, sw, sh = spot
                k = W / cw
                rx0, ry0 = (sx - x0) * k - 14, (sy - y0) * k - 14
                rx1, ry1 = (sx + sw - x0) * k + 14, (sy + sh - y0) * k + 14
                mask = Image.new("L", (W, H), int(120 * sa))
                md = ImageDraw.Draw(mask)
                md.rounded_rectangle((rx0, ry0, rx1, ry1), 16, fill=0)
                dark = Image.new("RGBA", (W, H), (2, 6, 14, 255)); dark.putalpha(mask)
                img.alpha_composite(dark)
                od = ImageDraw.Draw(img)
                od.rounded_rectangle((rx0, ry0, rx1, ry1), 16, outline=CYAN + (int(230 * sa),), width=3)
            canvas = Image.new("RGBA", (W, H), BG + (255,))
            canvas.alpha_composite(img.resize((1820, 1024), Image.BILINEAR), (50, 56))
            img = canvas
            if scene == "s7" and SAM and _sam_c is not None and cap_to_out(_sam_c) <= t < cap_to_out(_sam_e):
                a0, a1 = cap_to_out(_sam_c), cap_to_out(_sam_e)
                clip = sam_clip((t - a0) / (a1 - a0))
                fa = min(ease((t - a0) / 0.4), ease((a1 - t) / 0.4))
                img = Image.blend(img, clip, fa)
            if scene == "s4" and tin >= CU["s4"]["battery"] - 0.2:
                sa_ = ease((tin - CU["s4"]["battery"] + 0.2) / 0.6)
                dd = ImageDraw.Draw(img)
                for k_, (big, small, col) in enumerate((("135", "EMERGENCY LIGHTS & EXIT SIGNS", CYAN), ("~2 H", "NEWER UNITS", CYAN),
                                                         ("?", "OLDER UNITS · RUNTIME UNKNOWN", (148, 163, 184)), ("15 MIN", "MONTHLY TEST (not runtime)", CYAN))):
                    y = 150 + k_ * 112
                    box = Image.new("RGBA", (430, 96), (0, 0, 0, 0)); bd = ImageDraw.Draw(box)
                    rrect(bd, (0, 0, 429, 95), 14, fill=(8, 13, 24, 230), outline=col, width=2)
                    bd.text((22, 12), big, font=font(FB, 40), fill=col); bd.text((22, 62), small, font=font(FS, 19), fill=(220, 228, 238))
                    box.putalpha(box.getchannel("A").point(lambda v: int(v * sa_)))
                    img.alpha_composite(box, (W - 480, y))
            journey(img, scene, tin)
            for a, b, txt in LABELS.get(scene, []):
                if a <= tin < b:
                    al = min(ease((tin - a) / 0.35), ease((b - tin) / 0.35))
                    label(img, txt, al)
            if t >= END_START:
                img.alpha_composite(endcard(ease((t - END_START) / 0.8)))
        if not (t >= END_START + 0.8):
            subtitle(img, sub_at(t))
        enc.stdin.write(img.convert("RGB").tobytes())
        if n % 300 == 0:
            print(f"frame {n}/{nframes}", flush=True)
    enc.stdin.close(); enc.wait(); cap.kill()
    # SRT
    def ts(x):
        h, r = divmod(x, 3600); m_, s_ = divmod(r, 60)
        return f"{int(h):02d}:{int(m_):02d}:{int(s_):02d},{int((s_ % 1) * 1000):03d}"
    with open(f"{OUT}/FireRisk_Intelligence_Subtitles.srt", "w") as f:
        for i, (a, b, txt) in enumerate(SUBS, 1):
            f.write(f"{i}\n{ts(a)} --> {ts(b)}\n{txt}\n\n")
    print("video done", TOTAL)


if __name__ == "__main__":
    main()
