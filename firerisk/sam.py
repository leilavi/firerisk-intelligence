"""SAM 3.1 visual localization client and response parser. ORIGIN: NEW (2026-10-28, Hackathon).

What SAM does here: given ONE short English noun phrase (e.g. "fire extinguisher") and one still frame, it returns
boxes and masks around matching objects. That is all. A SAM result is supporting visual evidence for a Muse Spark
finding; it never sets or changes an alert, a severity, or the finding itself, and its confidence is a localization
score, not a fire-risk probability.

API facts (official docs read 2026-10-28: dev.meta.ai/docs/sam/*; verified live on the author's PC,
evidence/sam_check_20261028_202256.json and evidence/sam_check_20261028_202611.json):
  * POST {base}/responses, model `sam-3.1`, Bearer MODEL_API_KEY (same key as Muse Spark).
  * input = one user message with one `input_text` (the noun phrase) and one `input_image` (base64 data URL).
  * metadata values are strings: include_confidence "true", mask_encoding "one_bit".
  * output_text = one line per frame: `<Nf>id<|box;...;w;h[;c]|><|mask;...;data=H,W,<!|~>base85|>` records joined by
    commas. Empty output_text = valid "nothing located" answer. Live usage reports `images_processed`, tokens 0.
  * The live answer echoed `"store": true`; this client asks for `store: false`. If the endpoint rejects that
    parameter (HTTP 400 naming `store`), the request is sent once more without it and the fact is recorded.
Parsing uses Meta's official `meta-sam-parser` (requirements.txt); this module only normalizes its records.
"""

from __future__ import annotations

import base64
import json
import random
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from .ai.muse import MuseConfig

SAM_MODEL = "sam-3.1"
SAM_TIMEOUT_S = 120
RETRYABLE_HTTP = {429, 500, 502, 503, 504}
MAX_PHRASE_WORDS = 4


# --- errors (same `kind` convention as firerisk.ai.muse) -------------------------------------------------------
class SamError(Exception):
    kind = "error"


class SamNotConfigured(SamError):
    kind = "not_configured"


class SamAuthError(SamError):
    kind = "auth"


class SamRateLimited(SamError):
    kind = "rate_limited"


class SamTimeout(SamError):
    kind = "timeout"


class SamBadResponse(SamError):
    kind = "bad_response"


class SamBadRequest(SamError):
    """HTTP 400: permanent for this input - never resent unchanged."""
    kind = "bad_request"


class SamModelNotFound(SamError):
    kind = "model_not_found"


class SamServerError(SamError):
    kind = "server_error"


class SamNetworkError(SamError):
    kind = "network"


# --- phrase rules ----------------------------------------------------------------------------------------------
_FORBIDDEN_WORDS = {"person", "people", "man", "woman", "face", "faces", "human", "worker", "child", "body"}
_NEGATION = re.compile(r"\b(no|not|missing|without|absent|lack|lacking|none)\b")


def phrase_problem(phrase: str | None) -> str | None:
    """Why a text prompt is not a usable SAM noun phrase, or None when it is fine.

    Docs: one short noun phrase, one concept; no questions, lists, negations or locations. Project rule: never ask
    SAM to find people."""
    if not phrase or not phrase.strip():
        return "empty phrase"
    p = phrase.strip().lower()
    if len(p) > 40:
        return "phrase too long"
    if not re.fullmatch(r"[a-z][a-z0-9 \-]*", p):
        return "phrase must be plain English words (no punctuation, lists or non-English text)"
    words = p.split()
    if len(words) > MAX_PHRASE_WORDS:
        return f"phrase has more than {MAX_PHRASE_WORDS} words"
    if _NEGATION.search(p):
        return "phrase describes an absence"
    if set(words) & _FORBIDDEN_WORDS:
        return "phrase targets people"
    if re.search(r"\b(on|in|near|above|below|behind|next|left|right)\b", p):
        return "phrase contains a location"
    return None


# --- parsed result ---------------------------------------------------------------------------------------------
@dataclass
class SamObject:
    object_id: str
    frame_index: int
    box: dict                       # x1,y1,x2,y2 (half-open, source pixels), w,h
    confidence: float | None        # None = API did not send one (never 0)
    mask_svg_path: str | None = None
    mask_box: dict | None = None    # where the mask raster sits (source pixels) + raster size
    mask_error: str | None = None
    rle: dict | None = None         # COCO compressed RLE {"size":[h,w],"counts":str} of the box-local mask

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class SamParse:
    objects: list[SamObject]
    frame_sizes: dict[int, tuple[int, int]]        # frame_index -> (w, h) as reported in the answer
    diagnostics: list[dict] = field(default_factory=list)
    text_lines: int = 0                            # non-structured lines the parser kept
    complete: bool = True                          # False = some records were malformed / dropped

    @property
    def located(self) -> bool:
        return bool(self.objects)


_WH_RE = re.compile(r"<(\d+)f>")


def parse_output(text: str, media: str = "image", with_rle: bool = False) -> SamParse:
    """Normalize SAM output_text. Raises SamBadResponse when the text cannot be interpreted at all.

    Rules: empty text -> no objects (valid). Malformed records -> dropped and reported (complete=False), valid ones
    kept. A box outside its own frame size -> dropped. A mask that fails to decode -> object kept, no mask drawn.
    Confidence is passed through; it is never invented."""
    try:
        import meta_sam_parser as msp
    except ImportError as err:  # dependency missing on this computer
        raise SamNotConfigured("meta-sam-parser is not installed (run install.bat)") from err
    if text is None:
        text = ""
    if not isinstance(text, str):
        raise SamBadResponse("output_text is not a string")
    fmt = msp.image_segmentation_format() if media == "image" else msp.video_segmentation_format()
    parser = fmt.create_parser()
    try:
        parser.push(text)
        result = parser.finish(msp.CompletedOutcome()).result
    except Exception as err:  # parser contract violation - do not guess
        raise SamBadResponse(f"SAM output could not be parsed: {type(err).__name__}: {str(err)[:200]}") from None

    diags = [{"severity": d.severity, "code": d.code, "line": d.line} for d in result.diagnostics]
    complete = not any(d["severity"] == "error" for d in diags)
    sizes: dict[int, tuple[int, int]] = {}
    for line in text.splitlines():
        m = _WH_RE.match(line.strip())
        if m:
            wh = re.search(r"w=(\d+);h=(\d+)", line)
            if wh:
                sizes[int(m.group(1))] = (int(wh.group(1)), int(wh.group(2)))
    objs: dict[tuple[int, str], SamObject] = {}
    text_lines = 0
    for rec in result.records:
        if rec.kind == "text":
            if rec.text.strip():
                text_lines += 1
            continue
        fi = rec.frame.frame_index if rec.frame is not None else 0
        key = (fi, rec.object_id)
        if rec.kind == "box":
            box = {"x1": rec.left, "y1": rec.top, "x2": rec.right, "y2": rec.bottom,
                   "w": rec.right - rec.left, "h": rec.bottom - rec.top}
            fw, fh = sizes.get(fi, (None, None))
            bad = box["w"] <= 0 or box["h"] <= 0 or rec.left < 0 or rec.top < 0 or \
                (fw is not None and (rec.right > fw + 1 or rec.bottom > fh + 1))
            if bad:
                diags.append({"severity": "error", "code": "invalid_box", "line": None})
                complete = False
                continue
            objs[key] = SamObject(object_id=rec.object_id, frame_index=fi, box=box, confidence=rec.confidence)
        elif rec.kind == "mask":
            o = objs.get(key)
            if o is None:       # its box was rejected
                continue
            if o.confidence is None:
                o.confidence = rec.confidence
            b = rec.bounds
            o.mask_box = {"x": b.left, "y": b.top, "w": b.right - b.left, "h": b.bottom - b.top,
                          "raster_w": rec.mask.width, "raster_h": rec.mask.height}
            try:
                o.mask_svg_path = msp.decode_mask_to_svg_path(rec.mask)
                if with_rle:
                    r = msp.decode_mask_to_rle(rec.mask)
                    o.rle = {"size": list(r.size), "counts": r.counts if isinstance(r.counts, str)
                             else bytes(r.counts).decode("ascii")}
            except msp.InvalidSegmentationMaskError as err:
                o.mask_svg_path, o.rle = None, None
                o.mask_error = f"mask could not be decoded: {str(err)[:120]}"
                complete = False
    for o in objs.values():
        if o.mask_box is None and o.mask_error is None:
            o.mask_error = "mask missing or invalid in the answer"
            complete = False
    if text.strip() and not objs and not diags:
        # Text that is not the documented record grammar: an unexpected format, not a "no match".
        raise SamBadResponse("SAM output is not in the documented segmentation format")
    if text_lines:
        complete = False
    return SamParse(objects=list(objs.values()), frame_sizes=sizes, diagnostics=diags, text_lines=text_lines,
                    complete=complete)


# --- client ----------------------------------------------------------------------------------------------------
@dataclass
class SamResult:
    parse: SamParse
    model: str | None
    usage: dict | None
    seconds: float
    response_id: str | None
    images_billed: int | None
    store_disabled: bool               # True = request carried store:false and it was accepted

    @property
    def status(self) -> str:
        return "located" if self.parse.located else "not_located"

    @property
    def max_confidence(self) -> float | None:
        vals = [o.confidence for o in self.parse.objects if o.confidence is not None]
        return max(vals) if vals else None


def _output_text(body: dict) -> str:
    if not isinstance(body, dict) or not isinstance(body.get("output"), list):
        raise SamBadResponse(f"unexpected response shape: {str(body)[:200]}")
    texts = []
    for item in body["output"]:
        if isinstance(item, dict) and item.get("type") == "message":
            for c in item.get("content") or []:
                if isinstance(c, dict) and c.get("type") == "output_text":
                    if not isinstance(c.get("text"), str):
                        raise SamBadResponse("output_text part without text")
                    texts.append(c["text"])
    return "".join(texts)


class SamClient:
    """Non-streaming SAM 3.1 client. Retries 429 / 5xx / timeouts with exponential backoff (Muse client pattern);
    never retries an unchanged 400; reports 404 model_not_found as a model-access problem."""

    def __init__(self, config: MuseConfig | None = None, opener=None, sleep=time.sleep, model: str = SAM_MODEL):
        self.config = config or MuseConfig.load()
        self._open = opener or urllib.request.urlopen
        self._sleep = sleep
        self.model = model
        self.store_param_ok: bool | None = None     # learned from the first answer

    @property
    def configured(self) -> bool:
        return self.config.configured

    def _post(self, payload: dict) -> dict:
        req = urllib.request.Request(
            f"{self.config.base_url}/responses", data=json.dumps(payload).encode("utf-8"), method="POST",
            headers={"Authorization": f"Bearer {self.config.api_key}", "Content-Type": "application/json",
                     "Accept": "application/json"})
        try:
            with self._open(req, timeout=SAM_TIMEOUT_S) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as err:
            body = err.read().decode("utf-8", errors="replace")[:500]
            code = None
            try:
                e = json.loads(body).get("error")
                code = e.get("code") if isinstance(e, dict) else None
            except (json.JSONDecodeError, AttributeError):
                pass
            if err.code in (401, 403):
                raise SamAuthError(f"HTTP {err.code}") from None
            if err.code == 404 and (code == "model_not_found" or "model" in body.lower()):
                raise SamModelNotFound(f"HTTP 404 model_not_found: the API key may not have access to {self.model}") \
                    from None
            if err.code == 429:
                raise SamRateLimited("HTTP 429") from None
            if err.code in (408, 504):
                raise SamTimeout(f"HTTP {err.code}") from None
            if err.code in RETRYABLE_HTTP:
                raise SamServerError(f"HTTP {err.code}") from None
            if err.code == 400:
                raise SamBadRequest(f"HTTP 400: {body[:300]}") from None
            raise SamBadResponse(f"HTTP {err.code}: {body[:200]}") from None
        except TimeoutError as err:
            raise SamTimeout(str(err)) from None
        except urllib.error.URLError as err:
            if isinstance(err.reason, TimeoutError):
                raise SamTimeout(str(err)) from None
            raise SamNetworkError(f"network error: {err.reason}") from None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            raise SamBadResponse("non-JSON response") from None

    def locate(self, image_jpeg: bytes, phrase: str, *, retries: int = 3) -> SamResult:
        if not self.configured:
            raise SamNotConfigured("MODEL_API_KEY is not set (run setup_api_key.bat)")
        problem = phrase_problem(phrase)
        if problem:
            raise SamBadRequest(f"invalid phrase: {problem}")
        payload = {
            "model": self.model,
            "input": [{"role": "user", "content": [
                {"type": "input_text", "text": phrase.strip().lower()},
                {"type": "input_image",
                 "image_url": "data:image/jpeg;base64," + base64.b64encode(image_jpeg).decode("ascii")},
            ]}],
            "metadata": {"include_confidence": "true", "mask_encoding": "one_bit"},
        }
        if self.store_param_ok is not False:
            payload["store"] = False
        attempt = 0
        start = time.monotonic()
        while True:
            try:
                body = self._post(payload)
                break
            except SamBadRequest as err:
                # The only changed-request resend: drop `store` once if the endpoint rejects that parameter.
                if "store" in payload and "store" in str(err).lower():
                    payload.pop("store")
                    self.store_param_ok = False
                    continue
                raise
            except (SamRateLimited, SamTimeout, SamServerError, SamNetworkError):
                if attempt >= retries:
                    raise
                self._sleep(min(2 ** attempt, 30) + random.random())
                attempt += 1
        secs = time.monotonic() - start
        if isinstance(body, dict) and body.get("status") not in (None, "completed"):
            raise SamBadResponse(f"response status {body.get('status')}")
        text = _output_text(body)
        parsed = parse_output(text, media="image")
        usage = body.get("usage") if isinstance(body.get("usage"), dict) else None
        billed = usage.get("images_processed") if usage else None
        if "store" in payload:
            self.store_param_ok = True
        return SamResult(parse=parsed, model=body.get("model"), usage=usage, seconds=round(secs, 2),
                         response_id=body.get("id"), images_billed=billed if isinstance(billed, int) else None,
                         store_disabled=("store" in payload and body.get("store") is False))
