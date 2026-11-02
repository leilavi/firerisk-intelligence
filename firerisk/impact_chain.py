"""Chain of effects ("butterfly effect") for a fire-risk alert. ORIGIN: NEW (2026-11-01).

Question it answers for a reader who does not know the equipment: "this problem on equipment A - which other
equipment B does it affect, why, what can C then do, and what happens to people if it does?"

Deterministic and explainable:
  * a small graph of the building's systems: every link says WHY two parts are related and on what basis
    (asset relations already in the rule set, the confirmed drawing table, the technician's statement of
    2026-11-01, or a general hazard mechanism). A link that is not recorded is shown as "not established",
    never assumed;
  * the parts that have a recorded problem now (open, or a fault in the last 90 days) are taken from the alert's
    records and the linked equipment alerts; records without an Equipment_ID are matched by the equipment name in
    their title (marked as "matched by name");
  * from each part with a problem, the chain follows the links to the consequence for people, and on the way shows
    the other parts it depends on and THEIR recorded problems (e.g. the generator's starter batteries).
The chain is a possible sequence, not a prediction. Meta Muse Spark receives it and tells the story in plain
language with record citations (ai/investigation.py, field impact_story); the chain itself never depends on AI.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import datetime

RECENT_DAYS = 90
MAX_CHAINS = 5

BASIS = {
    "config": "asset relation in the rule set",
    "role": "equipment role (rule set)",
    "mechanism": "general hazard mechanism (rule set)",
    "technician": "technician's statement, 2026-11-01",
    "operator": "operations team statement, 2026-11-02",
    "drawings": "building drawings, counts checked by a person",
    "not_recorded": "not recorded",
}


@dataclass(frozen=True)
class Node:
    key: str
    label: str
    if_affected: str                 # plain language: what it means if this part is hit
    assets: tuple = ()
    words: tuple = ()                # folded words to match records that have no Equipment_ID
    outcome: bool = False            # consequence for people (end of a chain)


@dataclass(frozen=True)
class Link:
    a: str
    b: str
    why: str                         # plain language: why a problem on `a` reaches `b`
    basis: str
    confirmed: bool = True
    kind: str = "causes"             # "causes": a problem on a spreads to b; "needs": b needs a to work


NODES = {n.key: n for n in [
    Node("transformer", "Transformer and its room (MBA)", "The building can lose its grid supply.",
         ("P-BG.TTC110", "P-BG.TTC054"), ("mba", "tram bien ap", "bien ap")),
    Node("msb", "Main switchboard (MSB)", "Grid power to the building can be cut, or a short circuit can start in "
         "the switchboard.", ("P-BG.TTC046", "P-BG.TTC071", "P-BG.TTC076"), ("msb", "tu dien tong", "phan phoi tong")),
    Node("grid_supply", "Normal power supply of the whole building", "Lights, lifts, pumps and fans stop unless the "
         "standby generator takes over."),
    Node("generator", "Standby generator", "Nothing replaces the grid supply during an outage.", ("P-BG.TTC017",),
         ("may phat",)),
    Node("gen_batteries", "Generator starter batteries", "The generator may not start when it is needed.",
         ("P-BG.TTC217",), ("ac quy", "acquy", "binh ac")),
    Node("ats", "Automatic transfer switch (ATS) - one for the whole building", "There is only one ATS: if it fails, "
         "generator power reaches no floor at all."),
    Node("floor_panels", "Floor main panels (one per floor)", "The floor's circuits, including its emergency lights, "
         "lose supply."),
    Node("escape_lighting", "Emergency lights and exit signs", "They switch to their built-in batteries: about 2 hours "
         "when new, less on older fittings. The monthly test cuts power for only 15 minutes, so how long each fitting "
         "really lasts is not known."),
    Node("xlnt_blower", "Wastewater air blower AB-01A (plant room, B1)", "A seized motor that is run again can "
         "overheat.", ("P-BG.TTC167", "P-BG.TTC028", "P-BG.TTC226"), ("may thoi khi", "xlnt")),
    Node("fire_alarm", "Fire alarm / heat detection (basement)", "A fire in the basement may be detected late.",
         ("P-BG.TTC009",), ("bao chay", "dau bao")),
    Node("fire_pump", "Fire pump and fire water tank", "Less water may be available to fight a fire.",
         ("P-BG.TTC072",), ("bom chua chay", "bom pccc", "be nuoc pccc")),
    Node("smoke_fans", "Smoke exhaust fans (basement)", "Smoke may stay in the basement.", ("P-BG.TTC005",),
         ("hut khoi", "quat hut")),
    Node("pa_system", "Public-address / evacuation announcement system", "People on the other floors may not be "
         "told to leave in time.", (), ("loa", "phat thanh")),
    Node("basement_fire", "Smoke or fire in basement B1", "People in and above the basement are exposed to smoke.",
         outcome=False),
    Node("evacuation", "People evacuating the building", "Escape is slower or more dangerous.", outcome=True),
]}

LINKS = [
    Link("transformer", "msb", "The main switchboard is fed by the transformer; both are in the B1 electrical rooms.",
         "config"),
    Link("msb", "grid_supply", "The main switchboard distributes grid power to the whole building.", "role"),
    Link("msb", "basement_fire", "Water or a fault inside a switchboard can cause a short circuit, which can start a "
         "fire in the electrical room.", "mechanism"),
    Link("grid_supply", "ats", "When grid power is lost, one ATS switches the whole building to the standby "
         "generator.", "operator"),
    Link("gen_batteries", "generator", "The generator is started by these batteries.", "config", kind="needs"),
    Link("generator", "ats", "During a grid outage the generator is the only supply of the whole building, through "
         "the one ATS.", "operator", kind="needs"),
    Link("ats", "floor_panels", "The same ATS feeds the main panel of every floor (B1 to the roof), so a failure "
         "there reaches all 6 floors at once.", "operator"),
    Link("floor_panels", "escape_lighting", "Each floor's emergency lights and exit signs are fed from the floor "
         "control breaker inside the floor main panel - there is no dedicated emergency circuit.", "technician"),
    Link("escape_lighting", "evacuation", "In a long outage, fittings whose batteries run down - more likely on older "
         "ones - leave escape routes and exits dark or hard to find.", "mechanism"),
    Link("xlnt_blower", "basement_fire", "An overloaded or seized motor heats up; a burnt motor has already been "
         "recorded on this blower.", "mechanism"),
    Link("basement_fire", "fire_alarm", "A fire in the basement has to be detected by this system before people are "
         "warned.", "mechanism"),
    Link("basement_fire", "fire_pump", "Fighting the fire needs the fire pump and the fire water tank.", "mechanism"),
    Link("basement_fire", "smoke_fans", "Smoke in the basement has to be extracted by these fans.", "mechanism"),
    Link("basement_fire", "evacuation", "People have to leave the building.", "mechanism"),
    Link("pa_system", "evacuation", "People on every floor are told to leave by announcements; without them the "
         "evacuation of the upper floors can start late.", "mechanism"),
    Link("fire_alarm", "evacuation", "A late alarm leaves less time to get out.", "mechanism"),
    Link("smoke_fans", "evacuation", "Smoke on escape routes makes evacuation slower and more dangerous.", "mechanism"),
    Link("fire_pump", "evacuation", "Without fire water the fire can grow and smoke can reach the escape routes.",
         "mechanism"),
    # the generator supplies the whole building (operations team), so the fire pump and the smoke fans are behind the
    # same ATS during an outage; their exact circuits are not checked on the drawings
    Link("ats", "fire_pump", "On generator power the fire pump is supplied through the same ATS (whole building, "
         "operations team; its circuit is not checked on the drawings).", "operator"),
    Link("ats", "smoke_fans", "On generator power the smoke exhaust fans are supplied through the same ATS (whole "
         "building, operations team; their circuit is not checked on the drawings).", "operator"),
]
# building-specific power links: only used when the confirmed drawing table is present (no table = no building data)
NEEDS_POWER_TABLE = {("ats", "floor_panels"), ("floor_panels", "escape_lighting"), ("grid_supply", "ats"),
                     ("generator", "ats"), ("ats", "fire_pump"), ("ats", "smoke_fans")}
# without the table these stay visible as gaps, never followed as if known
GAPS_WITHOUT_TABLE = ["Which supply feeds the fire pump, and whether it is on the generator, is not recorded.",
                      "Which supply feeds the smoke exhaust fans, and whether they are on the generator, is not "
                      "recorded."]


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").replace("Đ", "D").replace("đ", "d"))
    s = "".join(c if c.isalnum() else " " for c in s if unicodedata.category(c) != "Mn")
    return " ".join(s.lower().split())


def _node_of(e) -> tuple[str | None, bool]:
    """(node key, matched_by_name)."""
    if e.asset_id:
        for n in NODES.values():
            if e.asset_id in n.assets:
                return n.key, False
    if not e.asset_id:
        t = _fold(f"{e.title} {e.text}")
        for n in NODES.values():
            if any(f" {w} " in f" {t} " or t.startswith(w) for w in n.words):
                return n.key, True
    return None, False


def _is_problem(e, now: datetime) -> bool:
    from .equipment import _is_fault
    if e.kind not in ("incident", "asset_service", "inspection_check") or "test_record" in e.flags:
        return False
    if e.kind == "inspection_check" and not _is_fault(e):
        return False
    if e.kind == "asset_service" and not _is_fault(e):
        return False
    recent = e.timestamp is not None and abs((now - e.timestamp).days) <= RECENT_DAYS
    return bool(e.is_open) or recent


def _condition(e, by_name: bool) -> dict:
    return {"evidence_id": e.evidence_id, "date": e.timestamp.date().isoformat() if e.timestamp else None,
            "title": e.title, "open": bool(e.is_open), "matched_by_name": by_name}


def _links(power_ok: bool) -> list[Link]:
    return [l for l in LINKS if power_ok or (l.a, l.b) not in NEEDS_POWER_TABLE]


def build(alert, evidence_index: dict, equipment_alerts, now: datetime, power=None, all_alerts=None) -> dict:
    """Chains of effects for one fire-risk alert (empty dict when no part of the graph has a recorded problem).
    For the whole-building alert ("Building") the chains start from the records of EVERY fire-risk alert: a problem
    in one floor's technical room can reach every floor, and that is what the building view must show."""
    power_ok = bool(power and getattr(power, "links", None))
    links = _links(power_ok)
    # problems per node, from the whole record set (a dependency's problem matters even if it is not in the alert)
    problems: dict[str, list[dict]] = {}
    for e in evidence_index.values():
        if not _is_problem(e, now):
            continue
        k, by_name = _node_of(e)
        if k:
            problems.setdefault(k, []).append(_condition(e, by_name))
    for v in problems.values():
        v.sort(key=lambda c: (not c["open"], c["date"] or ""), reverse=False)
    # where the chains start: parts with a problem that this alert is about (its records or linked equipment)
    ids = set(alert.evidence_ids) | set(getattr(alert, "context_ids", []) or [])
    by_id = {e.alert_id: e for e in equipment_alerts or []}
    scope = [alert] + ([a for a in all_alerts or [] if a is not alert] if alert.zone == "Building" else [])
    for a in scope[1:]:
        ids |= set(a.evidence_ids) | set(getattr(a, "context_ids", []) or [])
    for r in [r for a in scope for r in (getattr(a, "related_equipment", []) or [])]:
        ea = by_id.get(r.get("equipment_alert_id"))
        if ea:
            ids |= set(ea.evidence_ids)
    starts = []
    for k, conds in problems.items():
        hit = [c for c in conds if c["evidence_id"] in ids]
        if hit and not NODES[k].outcome:
            starts.append((k, hit))
    if not starts:
        return {}
    starts.sort(key=lambda kc: (-sum(c["open"] for c in kc[1]), -len(kc[1]), kc[0]))

    out_of = {}
    for l in links:
        out_of.setdefault(l.a, []).append(l)
    into = {}
    for l in links:
        into.setdefault(l.b, []).append(l)

    def paths(k, seen):
        if NODES[k].outcome:
            return [[k]]
        res = []
        for l in out_of.get(k, []):
            if l.confirmed and l.b not in seen:
                res += [[k] + p for p in paths(l.b, seen | {l.b})]
        return res

    lighting = power.floor_inventory("Building") if power_ok else {}
    light_total = sum(e["count"] for e in lighting.get("equipment", []) if e.get("count_known"))
    zone_inv = power.floor_inventory(alert.zone) if power_ok and alert.zone not in ("Building", "") else {}
    zone_total = sum(e["count"] for e in zone_inv.get("equipment", []) if e.get("count_known"))

    def node_view(k, nxt, path):
        n = NODES[k]
        label = n.label
        if k == "escape_lighting" and light_total:
            per_floor = ", ".join(f"{f} {sum(e['count'] for e in power.floor_inventory(f).get('equipment', []))}"
                                  for f in ("B1", "F1", "F2", "F3", "F4", "Roof") if power.floor_inventory(f))
            label = (f"{label} ({light_total} on all floors" + (f", {zone_total} on {alert.zone}" if zone_total else
                     f": {per_floor}" if alert.zone == "Building" else "") + ")")
        side = []          # other parts this step depends on (up to 2 links back) that have their own recorded problem
        todo, seen_up = ([] if n.outcome else [(k, 0)]), set(path)
        while todo:
            cur, depth = todo.pop(0)
            for l in into.get(cur, []):
                if l.a in seen_up or not l.confirmed or depth >= 2:
                    continue
                seen_up.add(l.a)
                if problems.get(l.a):
                    hop = next((x for x in into.get(k, []) if x.a == cur), None) if cur != k else None
                    via = f" {hop.why}" if hop else ""
                    side.append({"node": l.a, "label": NODES[l.a].label, "why": l.why + via, "basis": BASIS[l.basis],
                                 "relation": "depends_on" if l.kind == "needs" else "also_leads_here",
                                 "conditions": problems[l.a][:3]})
                todo.append((l.a, depth + 1))
        gaps = [{"label": NODES[l.b].label, "why": l.why} for l in out_of.get(k, []) if not l.confirmed]
        link = next((l for l in out_of.get(k, []) if l.b == nxt), None) if nxt else None
        return {"node": k, "label": label, "if_affected": n.if_affected, "conditions": problems.get(k, [])[:3],
                "depends_on": side, "not_established": gaps,
                "to_next": {"why": link.why, "basis": BASIS[link.basis]} if link else None}

    def split(p, main):
        return next((i for i, (x, y) in enumerate(zip(p, main)) if x != y), min(len(p), len(main)))

    # first one chain per part with a problem (the longest path), then alternatives that branch early
    mains, alts_all, covered = [], [], set()
    for k, hit in starts:
        if k in covered:                            # already shown as a step of an earlier chain
            continue
        ps = sorted(paths(k, {k}), key=lambda p: (-len(p), p))
        if not ps:
            continue
        mains.append((k, hit, ps[0]))
        covered |= set(ps[0])
        alts = sorted(ps[1:], key=lambda p: (split(p, ps[0]), -len(p)))
        alt = [p for p in alts if split(p, ps[0]) <= 2 and len(set(p) - set(ps[0])) >= 2][:1]
        alts_all += [(k, hit, p) for p in alt]
        covered |= set(alt[0]) if alt else set()
    cands = mains + alts_all
    # drop a chain that is fully contained in another one (e.g. "fire alarm -> evacuation" inside a longer chain)
    cands = [c for n, c in enumerate(cands)
             if not any(n != m and set(c[2]) < set(o[2]) or (n > m and set(c[2]) == set(o[2]))
                        for m, o in enumerate(cands))]
    cands.sort(key=lambda c: (-len(c[2]), -sum(x["open"] for x in c[1])))
    chains = [{"start": k, "start_label": NODES[k].label, "trigger": hit[:3],
               "steps": [node_view(x, p[i + 1] if i + 1 < len(p) else None, p) for i, x in enumerate(p)]}
              for k, hit, p in cands[:MAX_CHAINS]]
    gaps = sorted({g["why"] for c in chains for s in c["steps"] for g in s["not_established"]})
    if power_ok:
        from .power_links import LIGHT_BATTERY
        gaps += ["How long each older emergency light and exit sign really lasts on its battery: the monthly test "
                 f"cuts power for {LIGHT_BATTERY['monthly_test_minutes']} minutes only, and its results are not read "
                 "by the app yet.",
                 "The circuits of the fire pump and the smoke exhaust fans behind the ATS are not checked on the "
                 "drawings."]
    else:
        gaps += GAPS_WITHOUT_TABLE
    return {"chains": chains, "not_established": gaps,
            "note": "A possible sequence of effects built from recorded links, not a prediction. Each link states "
                    "its basis; links that are not recorded are listed as not established.",
            "basis": "rules + asset relations + confirmed drawing table + technician and operations team statements"}


def evidence_ids(chain: dict) -> list[str]:
    """Every record cited by a chain (so Meta Muse Spark can cite them)."""
    out: list[str] = []
    for c in chain.get("chains", []):
        for x in c["trigger"]:
            out.append(x["evidence_id"])
        for s in c["steps"]:
            out += [x["evidence_id"] for x in s["conditions"]]
            for d in s["depends_on"]:
                out += [x["evidence_id"] for x in d["conditions"]]
    return list(dict.fromkeys(out))
