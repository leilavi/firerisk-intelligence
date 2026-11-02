"""Scripted recording of the real dashboard in DEMO MODE for the hackathon video, version 5 (8 scenes, slow pacing).
Runs on the author's PC (private folder, never in the repository). Starts its own demo server on port 8777 with every
automatic analysis off (the screen does not change during a take), drives headless Microsoft Edge at 1920x1080 with
Playwright and records: browser frames + frames.json, marks.json (scene starts, zoom/spotlight targets with their
on-screen rectangles, for the editing step) and facts.json (the numbers shown, for the check).
Scene timing comes from timing5.json (voice-over length of each scene)."""
import base64, json, os, pathlib, subprocess, time, traceback, urllib.request

HERE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(os.environ.get("REC_ROOT") or HERE.parents[2])
OUT = HERE / "recording5"
OUT.mkdir(exist_ok=True)
for f in list(OUT.glob("*.*")) + list((OUT / "frames").glob("*.jpg") if (OUT / "frames").exists() else []):
    f.unlink()
TIMING = json.loads((HERE / "timing5.json").read_text(encoding="utf-8"))
SC, CUE = TIMING["scenes"], TIMING["cues"]
PORT = 8777
BASE = f"http://127.0.0.1:{PORT}"
env = dict(os.environ, FIRERISK_DEMO_MODE="1", FIRERISK_NO_BROWSER="1", FIRERISK_PORT=str(PORT), FIRERISK_AUTO_AI="1",
           FIRERISK_AUTO_SAM="0", FIRERISK_AUTO_VIDEO_AI="0", FIRERISK_DRIVE_VIDEOS="0", FIRERISK_SYNC_MINUTES="100000")
log = open(OUT / "server_log.txt", "w", encoding="utf-8")
srv = subprocess.Popen([str(ROOT / ".venv" / "Scripts" / "python.exe"), "-m", "firerisk.serve"], cwd=ROOT, env=env,
                       stdout=log, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
for _ in range(180):
    try:
        urllib.request.urlopen(BASE + "/api/status", timeout=3); break
    except Exception:
        time.sleep(1)

# wait until Meta Muse Spark has analysed the CURRENT evidence of both alerts shown in the video (the startup Drive
# sync can bring new records; the screen must not say "made on older evidence")
def _ai_current():
    out = {}
    for aid in ("ZONE-B1", "ZONE-Building"):
        try:
            a = json.loads(urllib.request.urlopen(BASE + "/api/alerts/" + aid, timeout=10).read())
            st = a.get("ai_status") or {}
            out[aid] = st.get("code") == "done" and st.get("result_is_current") is True
        except Exception:
            out[aid] = False
    return out
_t = time.monotonic()
while time.monotonic() - _t < 480:
    st = _ai_current()
    print("AI current:", st, round(time.monotonic() - _t), flush=True)
    if all(st.values()):
        break
    time.sleep(10)
time.sleep(3)

INIT = """
window.addEventListener('DOMContentLoaded', () => {
  const c = document.createElement('div'); c.id = '__cur';
  c.style.cssText = 'position:fixed;z-index:2147483647;left:0;top:0;width:24px;height:24px;margin:-12px 0 0 -12px;border-radius:50%;'
    + 'background:rgba(255,255,255,.9);box-shadow:0 0 0 3px rgba(34,211,238,.6),0 2px 10px rgba(0,0,0,.5);pointer-events:none;transition:transform .15s,box-shadow .15s';
  document.body.appendChild(c);
  document.addEventListener('mousemove', e => { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px'; }, true);
  document.addEventListener('mousedown', () => { c.style.transform = 'scale(.6)'; c.style.boxShadow = '0 0 0 14px rgba(34,211,238,.35)'; }, true);
  document.addEventListener('mouseup', () => { c.style.transform = 'scale(1)'; c.style.boxShadow = '0 0 0 3px rgba(34,211,238,.6),0 2px 10px rgba(0,0,0,.5)'; }, true);
  const st = document.createElement('style');
  st.textContent = `#notice{display:none!important}
    .rec-dim .cf-node{opacity:.32;transition:opacity .45s,box-shadow .45s}
    .rec-dim .cf-node.rec-done{opacity:.62}
    .rec-dim .cf-node.rec-on{opacity:1;box-shadow:0 0 0 3px #22D3EE,0 0 30px rgba(34,211,238,.55)}
    .rec-dim .cf-arrow{opacity:.35;transition:opacity .45s}
    .rec-dim .cf-arrow.rec-on{opacity:1}
    .rec-dim .cf-arrow.rec-on .cf-ar{color:#22D3EE;text-shadow:0 0 12px #22D3EE}
    .rec-dim .cf-dep.rec-on{box-shadow:0 0 0 2px #F472B6,0 0 22px rgba(244,114,182,.5);transition:box-shadow .45s}
    .rec-hl{box-shadow:0 0 0 3px #22D3EE,0 0 26px rgba(34,211,238,.5)!important;border-radius:8px;transition:box-shadow .4s}`;
  document.head.appendChild(st);
});"""
SMOOTH = """async ([y, ms]) => {
  const start = window.scrollY, d = y - start, t0 = performance.now();
  await new Promise(res => { const f = now => { const p = Math.min(1, (now - t0) / ms); const e = p < .5 ? 2*p*p : 1 - Math.pow(-2*p+2, 2)/2;
    window.scrollTo(0, start + d * e); p < 1 ? requestAnimationFrame(f) : res(); }; requestAnimationFrame(f); });
  return window.scrollY; }"""

from playwright.sync_api import sync_playwright

marks, facts, errors = [], {}, []
try:
    with sync_playwright() as p:
        b = p.chromium.launch(channel=os.environ.get("REC_CHANNEL", "msedge") or None, headless=True)
        ctx = b.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
        ctx.add_init_script(INIT)
        page = ctx.new_page()
        page.goto(BASE + "/#/"); page.wait_for_selector(".bchain", timeout=90000); page.wait_for_timeout(2500)
        t0 = time.monotonic()
        FR = OUT / "frames"; FR.mkdir(exist_ok=True)
        frames = []
        cdp = ctx.new_cdp_session(page)

        def on_frame(ev):
            k = len(frames)
            (FR / f"s{k:06d}.jpg").write_bytes(base64.b64decode(ev["data"]))
            frames.append({"f": f"s{k:06d}.jpg", "t": round(time.monotonic() - t0, 3)})
            try:
                cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]})
            except Exception:
                pass
        cdp.on("Page.screencastFrame", on_frame)
        SC_ARGS = {"format": "jpeg", "quality": 92, "maxWidth": 1920, "maxHeight": 1080, "everyNthFrame": 1}
        cdp.send("Page.startScreencast", SC_ARGS)
        page.set_default_timeout(8000)
        restarts = [0]

        def kick():
            """Watchdog: if the screencast went quiet (a lost ack stops it), restart it - a static page only costs a frame."""
            last = frames[-1]["t"] if frames else 0
            if time.monotonic() - t0 - last > 0.9:
                try:
                    cdp.send("Page.stopScreencast"); cdp.send("Page.startScreencast", SC_ARGS); restarts[0] += 1
                except Exception:
                    pass

        now = lambda: round(time.monotonic() - t0, 3)
        cur = {"start": 0.0, "name": ""}

        def scene(name):
            cur["start"] = time.monotonic(); cur["name"] = name
            marks.append({"t": now(), "type": "scene", "name": name}); print(now(), "scene", name, flush=True)

        def hold(s):
            end = time.monotonic() + max(0, s)
            while True:
                kick()
                left = end - time.monotonic()
                if left <= 0:
                    break
                page.wait_for_timeout(int(min(left, 0.25) * 1000))

        def until(t_rel):                      # wait until scene-relative time
            hold(cur["start"] + t_rel - time.monotonic())

        def rect(loc):
            try:
                bb = loc.bounding_box()
                return [round(bb["x"]), round(bb["y"]), round(bb["width"]), round(bb["height"])] if bb else None
            except Exception:
                return None

        def zoom(loc_or_rect, scale=1.5, spot=False, name=""):
            r = loc_or_rect if isinstance(loc_or_rect, list) else rect(loc_or_rect)
            marks.append({"t": now(), "type": "zoom", "rect": r, "scale": scale if r else 1.0, "spot": bool(spot and r),
                          "scene": cur["name"], "name": name})

        def zoom_out(name=""):
            marks.append({"t": now(), "type": "zoom", "rect": None, "scale": 1.0, "spot": False, "scene": cur["name"], "name": name})

        def scroll_to(loc, offset=0.4, ms=1200):
            """Scroll so the element's top sits at `offset` of the viewport height."""
            try:
                bb = loc.bounding_box()
                if not bb:
                    loc.scroll_into_view_if_needed(); bb = loc.bounding_box()
                y = page.evaluate("window.scrollY") + bb["y"] - 1080 * offset
                page.evaluate(SMOOTH, [max(0, y), ms]); hold(0.15)
            except Exception as e:
                errors.append(f"{cur['name']} scroll: {e}")

        def scroll_y(y, ms=1200):
            page.evaluate(SMOOTH, [y, ms]); hold(0.15)

        def move(loc, click=False, steps=28):
            try:
                bb = loc.bounding_box()
                if not bb:
                    return False
                x, y = bb["x"] + min(bb["width"] / 2, 70), bb["y"] + bb["height"] / 2
                page.mouse.move(x, y, steps=steps); hold(0.25)
                if click:
                    page.mouse.down(); hold(0.12); page.mouse.up()
                return True
            except Exception as e:
                errors.append(f"{cur['name']} move: {e}"); return False

        def first(sel, has_text=None):
            loc = page.locator(sel, has_text=has_text) if has_text else page.locator(sel)
            return loc.first if loc.count() else None

        def step(fn):
            try:
                fn()
            except Exception:
                errors.append(f"{cur['name']}: {traceback.format_exc(limit=2)}"); print("ERR", errors[-1][:300], flush=True)

        def close_drawer():
            try:
                if page.locator("#drawer:not([hidden])").count():
                    page.locator("#drawer-close").click(timeout=3000); hold(0.3)
            except Exception:
                pass

        def get(path):
            return page.evaluate("async p => (await fetch(p)).json()", path)

        # ================= scene 2: product, overview only =================
        scene("s2")
        def s2():
            page.mouse.move(960, 600, steps=10)
            zoom_out("overview")
            until(5.5)
            mk = first("#bmap .mk.high") or first("#bmap .mk")
            mp = page.locator("#bmap")
            if mk:
                move(mk, steps=50)
            zoom(mp, 1.5, spot=True, name="risk_map")
            until(CUE["s2"]["connects"] + 0.6)
            kpis = page.locator(".kpis")
            move(page.locator(".kpi").nth(4), steps=50)
            zoom(kpis, 1.45, spot=True, name="kpis")
            until(SC["s2"] - 1.2)
            zoom_out()
        step(s2)

        # ================= scene 3: rule engine =================
        until(SC["s2"])
        scene("s3")
        def s3():
            bc = page.locator(".bchain")
            scroll_to(bc, 0.10, 2000)
            zoom(bc, 1.45, spot=True, name="bchain")
            move(bc.locator(".bc-list li").first, steps=50)
            until(5.6)
            link = page.locator(".bchain a", has_text="See each step")
            zoom_out(); scroll_to(link, 0.55, 1100)
            move(link, steps=45); hold(0.5)
            move(link, click=True)
            page.wait_for_selector(".cf-block .cf-wrap[open] .cf", timeout=15000); hold(0.6)
            cf = page.locator(".cf-wrap[open] .cf")
            nodes = cf.locator(".cf-node")
            labels = [n.strip() for n in nodes.locator(".cf-label").all_inner_texts()]
            facts["chain1_labels"] = labels
            idx = lambda k, d: next((i for i, l in enumerate(labels) if k in l), d)
            ats = nodes.nth(idx("ATS", 3)); arr = cf.locator(".cf-arrow").nth(idx("ATS", 3))
            scroll_to(ats, 0.28, 1800)
            until(CUE["s3"]["ats"] - 0.3)
            ra, rb = rect(ats), rect(arr)
            zoom(([min(ra[0], rb[0]), ra[1], max(ra[0] + ra[2], rb[0] + rb[2]) - min(ra[0], rb[0]), rb[1] + rb[3] - ra[1]]
                  if ra and rb else ats), 1.5, spot=True, name="ats_basis")
            move(ats.locator(".cf-label"), steps=50); hold(1.6)
            dep = ats.locator(".cf-dep").first
            if dep.count():
                move(dep, steps=40)
            hold(1.2); move(arr, steps=40)
            until(CUE["s3"]["lights"] + 0.6)
            li = nodes.nth(idx("Emergency lights", 5))
            scroll_to(nodes.nth(idx("Floor main panels", 4)), 0.25, 1800)
            zoom(li, 1.55, spot=True, name="lights"); move(li.locator(".cf-label"), steps=50)
            until(SC["s3"] - 0.8)
            zoom_out()
        step(s3)

        # ================= scene 4: Muse Spark + domino =================
        until(SC["s3"])
        scene("s4")
        def s4():
            story = first(".cf-block .cf-story")
            if story:
                scroll_to(story, 0.12, 1800)
                zoom(story.locator(".cf-head"), 1.6, spot=True, name="story_headline")
                move(story.locator(".cf-head"), steps=60)
                facts["story_headline_shown"] = story.locator(".cf-head").inner_text()
            cf = page.locator(".cf-wrap[open] .cf")
            nodes = cf.locator(".cf-node")
            labels = [n.strip() for n in nodes.locator(".cf-label").all_inner_texts()]
            find = lambda k, d: next((i for i, l in enumerate(labels) if k in l), d)
            order = [("water", find("Transformer", 0)), ("grid", find("Normal power", 2)), ("gen", find("ATS", 3)),
                     ("lights", find("Emergency lights", 5))]
            until(CUE["s4"]["water"] - 1.2)
            zoom_out()
            page.evaluate("() => document.querySelector('.cf-wrap[open] .cf').classList.add('rec-dim')")
            def light(i, dep=False):
                page.evaluate("""([i, dep]) => { const ns = [...document.querySelectorAll('.cf-wrap[open] .cf .cf-node')];
                    const as = [...document.querySelectorAll('.cf-wrap[open] .cf .cf-arrow')];
                    ns.forEach((n, k) => { n.classList.toggle('rec-on', k === i); n.classList.toggle('rec-done', k < i); });
                    as.forEach((a, k) => a.classList.toggle('rec-on', k === i - 1));
                    ns[i] && ns[i].querySelectorAll('.cf-dep').forEach(d => d.classList.toggle('rec-on', dep)); }""", [i, dep])
            shown = -1
            for k, (cue, i) in enumerate(order):
                until(CUE["s4"][cue] - 0.6)
                for j in range(shown + 1, i):
                    light(j); scroll_to(nodes.nth(j), 0.32, 900); hold(0.7)
                n = nodes.nth(i)
                light(i, dep=(cue == "gen"))
                scroll_to(n, 0.30, 1300)
                mark_t = {"water": "c_water", "grid": "c_grid", "gen": "c_gen", "lights": "c_lights"}[cue]
                if cue == "gen":
                    dep = n.locator(".cf-dep").first
                    zoom(n, 1.4, spot=True, name="ats_gen_batteries"); move(dep if dep.count() else n, steps=50)
                elif cue == "lights":
                    zoom(n, 1.4, spot=True, name="lights_node"); move(n.locator(".cf-label"), steps=50)
                    until(CUE["s4"]["battery"] - 0.3)
                    zoom(n.locator(".cf-if"), 2.0, spot=True, name="battery_text"); move(n.locator(".cf-if"), steps=70)
                else:
                    zoom(n, 1.45, spot=True, name=f"domino_{cue}")
                    conds = n.locator(".cf-cond")
                    move(conds.first if conds.count() else n.locator(".cf-label"), steps=50)
                marks.append({"t": now(), "type": "cue", "name": mark_t})
                shown = i
            facts["domino_nodes"] = [labels[i] for _, i in order]
            until(SC["s4"] - 0.8)
            page.evaluate("() => { const c = document.querySelector('.cf-wrap[open] .cf'); c.classList.remove('rec-dim'); c.querySelectorAll('.rec-on,.rec-done').forEach(x => x.classList.remove('rec-on','rec-done')); }")
        step(s4)

        # ================= scene 5: evidence + equipment cross-link =================
        until(SC["s4"])
        scene("s5")
        def s5():
            cf = page.locator(".cf-wrap[open] .cf")
            arr = cf.locator(".cf-arrow").nth(3)
            scroll_to(arr, 0.40, 1300)
            zoom(arr, 1.9, spot=True, name="arrow_basis"); move(arr, steps=50)
            until(CUE["s5"]["record"] - 1.6)
            chip = cf.locator(".cf-cond .chip").first
            scroll_to(chip, 0.40, 1200)
            zoom_out(); move(chip, click=True, steps=40)
            page.wait_for_selector("#drawer:not([hidden])", timeout=10000); hold(0.6)
            dr = page.locator("#drawer")
            zoom(dr, 1.3, spot=True, name="record_drawer")
            move(dr.locator("dl, .kv, table").first if dr.locator("dl, .kv, table").count() else dr, steps=50)
            facts["drawer_text"] = dr.inner_text()[:1200]
            hold(3.6)
            close_drawer(); zoom_out()
            move(page.locator('nav a[data-nav="equipment"]'), click=True, steps=35)
            page.wait_for_selector("button.icard", timeout=15000); hold(0.6)
            row = first("button.icard", "water seepage") or first("button.icard", "MSB")
            if row:
                zoom(row, 1.6, spot=True, name="eq_row"); move(row, steps=30); hold(0.6); move(row, click=True)
                page.wait_for_selector("#drawer:not([hidden])", timeout=10000); hold(0.5)
            lk = first('#drawer a.mini[href^="#/fire/"]')
            if lk:
                lk.scroll_into_view_if_needed(); hold(0.4)
                zoom(lk, 1.8, spot=True, name="linked_fire_risk"); move(lk, steps=40)
                facts["eq_link_text"] = lk.inner_text()
                hold(2.2)
                zoom_out(); move(lk, click=True); hold(0.8)
            if "#/fire/" not in page.url:
                close_drawer(); page.goto(BASE + "/#/fire/ZONE-B1")
            page.wait_for_selector(".cf-block", timeout=15000)
            facts["s5_back_url"] = page.url
            gaps = first(".cf-block p", "Links not recorded")
            if gaps:
                scroll_to(gaps, 0.45, 1500)
                zoom(gaps, 1.8, spot=True, name="not_established"); move(gaps, steps=45)
                facts["gaps_text"] = gaps.inner_text()
        step(s5)

        # ================= scene 6: agent =================
        until(SC["s5"])
        scene("s6")
        def s6():
            zoom_out(); close_drawer()
            if "ZONE-B1" not in page.url:
                page.goto(BASE + "/#/fire/ZONE-B1"); page.wait_for_selector(".dhead", timeout=15000)
            scroll_y(0, 600)
            move(first('[data-jump="s4"]'), click=True, steps=30); hold(1.0)
            ag = first("#s4 details.agent")
            if ag:
                scroll_to(ag, 0.12, 900)
                move(ag.locator("summary"), click=True, steps=30); hold(0.5)
                zoom(ag, 1.3, spot=True, name="agent_trace")
                facts["agent_text"] = ag.inner_text()[:2500]
                until(CUE["s6"]["lookups"])
                st = ag.locator("ol.agent-steps > li:not(.note)")
                tool = first("#s4 details.agent ol.agent-steps > li", "get_fire_safety_supply") or \
                       first("#s4 details.agent ol.agent-steps > li", "safety supply")
                for k in range(min(st.count(), 3)):
                    move(st.nth(k), steps=20); hold(0.3)
                if tool:
                    move(tool, steps=30); zoom(tool, 2.0, spot=True, name="tool_call")
                    facts["tool_call_text"] = tool.inner_text()
            until(CUE["s6"]["cite"] - 0.3)
            ck = first("#s4 .cite-ok")
            if ck:
                scroll_to(ck, 0.45, 1300)
                zoom(ck, 2.1, spot=True, name="cite_ok"); move(ck, steps=45)
                facts["cite_text"] = ck.inner_text()
            until(CUE["s6"]["rules"] - 0.3)
            pr = first("#s4 p.small", "official rule severity")
            if pr:
                scroll_to(pr, 0.45, 1200)
                zoom(pr, 1.8, spot=True, name="rule_vs_ai"); move(pr, steps=45)
                facts["rule_vs_ai"] = pr.inner_text()
        step(s6)

        # ================= scene 7: survey videos + SAM 3.1 =================
        until(SC["s6"])
        scene("s7")
        def s7():
            zoom_out(); close_drawer()
            move(page.locator('nav a[data-nav="overview"]'), click=True, steps=30)
            page.wait_for_selector("#vf-h", timeout=15000); hold(0.4)
            scroll_to(page.locator("#vf-h"), 0.08, 1600)
            panel = page.locator("#vf-h").locator("xpath=ancestor::section[1]")
            zoom(panel, 1.15, spot=False, name="vf_panel")
            best = first(".vs-top .icard", "Cable lying") or first(".vs-top .icard")
            until(3.4)
            if best:
                scroll_to(best, 0.5, 800)
                move(best, click=True, steps=40)
                page.wait_for_selector("#drawer:not([hidden])", timeout=10000); hold(0.6)
                dr = page.locator("#drawer")
                zoom(dr, 1.25, spot=False, name="finding_drawer")
                facts["finding_drawer"] = dr.inner_text()[:1500]
                until(6.0)
                marks.append({"t": now(), "type": "cue", "name": "sam_clip_start"})
                hold(5.0)                                  # replaced in the edit by the SAM 3.1 frame sequence
                marks.append({"t": now(), "type": "cue", "name": "sam_clip_end"})
                loc = first("#drawer .ev-sam")
                if loc:
                    loc.scroll_into_view_if_needed(); hold(0.3)
                    zoom(loc, 1.7, spot=True, name="sam_located"); move(loc, steps=35)
                    facts["sam_text"] = loc.inner_text()[:400]
                hold(1.8)
                link = first("#drawer a.mini")
                if link:
                    link.scroll_into_view_if_needed(); hold(0.3)
                    zoom(link, 1.8, spot=True, name="finding_link"); move(link, steps=35)
                    facts["finding_link"] = link.inner_text()
                    until(SC["s7"] - 1.4)
                    zoom_out(); move(link, click=True); hold(0.8)
                    if "#/fire/" not in page.url:
                        close_drawer(); page.goto(BASE + "/#/fire/ZONE-B1")
                    page.wait_for_selector(".dhead", timeout=15000)
        step(s7)

        # ================= scene 8: actions + decision =================
        until(SC["s7"])
        scene("s8")
        def s8():
            zoom_out(); close_drawer()
            if "#/fire/" not in page.url:
                page.goto(BASE + "/#/fire/ZONE-B1"); page.wait_for_selector(".dhead", timeout=15000)
            scroll_y(0, 500)
            move(first('[data-jump="s5"]'), click=True, steps=30); hold(1.0)
            facts["actions"] = page.locator("#s5 li").all_inner_texts()
            picks = [first("#s5 li", k) for k in ("Inspect MBA and MSB", "generator starter batteries")]
            picks = [x for x in picks if x]
            if len(picks) < 2:
                ai = page.locator("#s5 li", has_text="—")
                picks = [ai.nth(i) for i in range(min(2, ai.count()))]
            facts["action_picks"] = [x.inner_text()[:200] for x in picks]
            for k, x in enumerate(picks):
                until(CUE["s8"]["actions"] - 1.0 + k * 3.0)
                scroll_to(x, 0.40, 1000)
                zoom(x, 1.65, spot=True, name="action"); move(x, steps=35)
            until(CUE["s8"]["decision"] - 0.3)
            zoom_out(); scroll_y(0, 1100)
            ver = page.locator("aside.side section.q").nth(1)
            zoom(ver, 1.8, spot=True, name="verification"); move(ver.locator("h2"), steps=40)
            facts["verification"] = ver.inner_text()[:600]
            until(CUE["s8"]["end"] - 1.6)
            zoom_out()
            move(page.locator('nav a[data-nav="overview"]'), click=True, steps=30)
            page.wait_for_selector(".bchain", timeout=15000)
            page.mouse.move(1500, 900, steps=10)
            until(SC["s8"] + 1.5)
        step(s8)
        marks.append({"t": now(), "type": "end"})

        # ---- assets for the edit: blurred survey frames (demo mode serves only blurred copies) + SAM boxes ----
        try:
            import zipfile
            vf = get("/api/video-findings")
            (OUT / "video_findings.json").write_text(json.dumps(vf, ensure_ascii=False, indent=1), encoding="utf-8")
            urls = []
            for f in vf.get("findings", []):
                for fr in ((f.get("localization") or {}).get("frames") or []):
                    if fr.get("frame_file"):
                        urls.append("/api/frames/" + fr["frame_file"])
            urls = list(dict.fromkeys(urls))[:200]
            with zipfile.ZipFile(OUT / "frames_blurred.zip", "w") as z:
                for u in urls:
                    b64 = page.evaluate("""async u => { const r = await fetch(u); if (!r.ok) return null;
                        const b = new Uint8Array(await r.arrayBuffer()); let s = ''; for (let i = 0; i < b.length; i++) s += String.fromCharCode(b[i]);
                        return btoa(s); }""", u)
                    if b64:
                        z.writestr(u.replace("/api/frames/", "").replace("/", "_"), base64.b64decode(b64))
            facts["frames_exported"] = len(urls)
        except Exception as e:
            errors.append(f"assets: {e}")
        facts["screencast_restarts"] = restarts[0]

        # facts for the numbers check
        bld = get("/api/building")
        facts["building_chain"] = bld.get("building_chain")
        for aid in ("ZONE-Building", "ZONE-B1"):
            a = get("/api/alerts/" + aid)
            inv = a.get("investigation") or {}
            facts[aid] = {"severity": a["alert"]["severity"], "ai_status": a.get("ai_status"), "created_at": inv.get("created_at"),
                          "prompt_version": inv.get("prompt_version"), "validation": inv.get("validation"),
                          "impact_story": (inv.get("result") or {}).get("impact_story"),
                          "actions": [x.get("action") for x in ((inv.get("result") or {}).get("recommended_actions") or [])]}
        cdp.send("Page.stopScreencast")
        (OUT / "frames.json").write_text(json.dumps(frames), encoding="utf-8")
        ctx.close(); b.close()
finally:
    (OUT / "marks.json").write_text(json.dumps(marks, indent=1), encoding="utf-8")
    (OUT / "facts.json").write_text(json.dumps(facts, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (OUT / "errors.txt").write_text("\n".join(errors), encoding="utf-8")
    srv.terminate()
    print("DONE", len(errors), "errors", flush=True)
