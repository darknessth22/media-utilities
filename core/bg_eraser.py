"""Background removal and object erasing — offline after first use.

Two operations live here:

* `remove_background()` — strip the background with a selectable model.
* `erase_region()`      — delete the object(s) the user painted over and heal
                          the hole, leaving the rest of the image untouched.

Segmentation models
-------------------
rembg's default is u2net (2020). Measured against BiRefNet on a portrait and a
bicycle, u2net dragged background colour into hair and lost thin structure
(wheel spokes) entirely, while BiRefNet resolved both cleanly. BiRefNet is the
default here, with u2net kept as the fast option. All of these ship with the
pinned rembg, so only the ONNX weights download on first use.

Healing
-------
`cv2.inpaint` (TELEA) only diffuses surrounding colour inward, so it leaves an
obvious blurred smear on anything textured — measured on a rainy-window shot
and a printed map it wiped out the droplets and the map lines completely.
**LaMa** is a generative inpainting model exported to ONNX (~198 MB) that
reconstructs plausible texture instead; on those same images it rebuilt
railings, droplets, roads and city dots so the fill is invisible. It runs on
the `onnxruntime` rembg already pulls in — no torch, no new dependency — at
roughly 1.5-2 s per fill on CPU.

LaMa is therefore the default, with the fast blur-fill kept for when the
weights are absent or an instant result is wanted.
"""
from __future__ import annotations

import os

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}

# id -> (rembg session name, approx weight download in MB)
# Ordered fastest-to-best; the GUI builds its dropdown from this.
MODELS: dict[str, tuple[str, int]] = {
    "fast": ("u2net", 176),
    "balanced": ("birefnet-general-lite", 224),
    "best": ("birefnet-general", 928),
    "portrait": ("birefnet-portrait", 928),
    "anime": ("isnet-anime", 168),
}
DEFAULT_MODEL = "balanced"

# Selection shapes an erase request can carry.
SHAPE_BRUSH = "brush"
SHAPE_LASSO = "lasso"
SHAPE_RECT = "rect"
SHAPE_ELLIPSE = "ellipse"
# "Smart" shapes don't erase what was drawn — the drawn area only tells the
# segmentation model *which object* is meant, and the object's own outline is
# what gets erased. This is the phone-style "tap the thing to remove it".
SHAPE_SMART = "smart"

# How far a smart selection is allowed to grow beyond the exact region the
# pointer landed on. This is the fix for "I circled one of three people and it
# selected all three": a salient-object model returns ONE connected blob for
# subjects that touch, so completing SAM's mask with that blob swallowed the
# neighbours. Sensitivity now decides how much completion is allowed.
#
#   SENS_TIGHT   SAM only. Exactly the instance under the pointer — the right
#                choice for one person in a crowd, or one object in a pile.
#   SENS_BALANCED SAM, plus the subject blob only when it is not dramatically
#                bigger than SAM's own mask (i.e. it plausibly IS the same
#                object rather than a merged group).
#   SENS_LOOSE   Always complete into the whole subject blob. Best for a lone
#                subject on a plain background, where SAM alone can return just
#                a sleeve or a face.
SENS_TIGHT = "tight"
SENS_BALANCED = "balanced"
SENS_LOOSE = "loose"
DEFAULT_SENSITIVITY = SENS_BALANCED

# Above this ratio (subject blob area / SAM instance area) the blob is assumed
# to be several merged subjects and is rejected at balanced sensitivity.
# Measured on a three-worker shot: SAM gave one worker at 8.4% of the frame, the
# merged blob was 27.1% -> ratio 3.2. A single person completed from a partial
# SAM mask sat at 1.4-2.1, so 2.6 separates the two cases.
_MERGE_RATIO = 2.6

# Segment-Anything, used for smart selection. rembg ships the session; the
# weights (~360 MB for vit_b: encoder + decoder) download on first use into
# rembg's own cache, so nothing extra needs bundling.
SAM_SESSION = "sam"
_SAM_SIZE_MB = 360
# Subject/object segmenter used to complete a SAM selection. SAM segments the
# *region* under the pointer — clicking a face returned only the facial skin,
# not the person (no hair, glasses or shirt). A salient-object model returns the
# whole subject, so the two are combined: SAM anchors WHICH instance was meant,
# the salient component supplies the whole extent. Weights are the same
# BiRefNet file the Remove Background tab already downloads, so smart select
# usually costs no extra download.
# Subject segmenter used to complete a smart selection. Benchmarked four
# candidates on a person, a bicycle (thin spokes), two touching workers and a
# chair, scoring boundary detail rather than raw coverage:
#
#   birefnet-general-lite  214 MB  ~6 s   balanced; the default
#   isnet-general-use      171 MB  ~1 s   agrees with lite at IoU 0.87-0.997
#   birefnet-general       928 MB  ~9 s   sharpest edges
#   birefnet-dis           928 MB  ~17 s  best boundary detail on objects BUT
#                                         failed on a person (cut off the shirt
#                                         with a ragged edge) — not a safe default
#
# No single model wins everywhere, so this follows the model the user picked for
# background removal instead of being fixed. Reusing that choice also means smart
# select usually needs no extra download.
_SUBJECT_FOR_MODEL: dict[str, str] = {
    "fast": "isnet-general-use",           # u2net has no matching subject model
    "balanced": "birefnet-general-lite",
    "best": "birefnet-general",
    "portrait": "birefnet-portrait",
    "anime": "isnet-anime",
}
SUBJECT_SESSION = "birefnet-general-lite"  # fallback when no model is given
_subject_session = None
_subject_session_name: str | None = None
# Exact detected masks, keyed by (image, prompt). The contours handed to the GUI
# are simplified for cheap drawing and must NEVER be used as the erase mask —
# doing so turned a bicycle into a filled disc, so LaMa was asked to invent a
# huge solid blob and averaged the dark frame into it.
_detected_masks: dict = {}
# The subject mask depends only on the image, so cache it per image — otherwise
# every extra mark re-runs a multi-second model.
_subject_cache: dict = {}
_sam_session = None
# SAM runs an expensive encoder over the whole image, then a cheap decoder per
# prompt. rembg's `remove()` redoes both every call (~3.7 s), which is far too
# slow to preview a selection interactively. Caching the embedding per image
# makes each extra click ~0.1 s.
_sam_embed_cache: dict = {}

_HEAL_RADIUS = 9

# Heal engines.
HEAL_LAMA = "lama"     # generative, reconstructs texture (default)
HEAL_FAST = "fast"     # cv2.inpaint diffusion — instant but blurs texture
HEAL_NONE = "none"     # leave the area transparent

# LaMa ONNX export. Downloaded on demand, like rembg's own weights, and cached
# beside the other AI packages so it survives app updates.
_LAMA_URL = "https://huggingface.co/Carve/LaMa-ONNX/resolve/main/lama_fp32.onnx"
_LAMA_FILE = "lama_fp32.onnx"
_LAMA_SIZE_MB = 198
_LAMA_INPUT = 512      # the export is fixed at 512x512

_lama_session = None   # cached across calls; loading costs ~1 s


def _fail(msg: str) -> dict:
    return {"success": False, "file_path": "", "error": msg}


def _validate_source(input_path: str) -> str | None:
    """Return an error message when *input_path* is unusable, else None."""
    if not os.path.isfile(input_path):
        return "Source file not found."
    ext = os.path.splitext(input_path)[1].lower()
    if ext not in IMAGE_EXTS:
        return f"Unsupported format '{ext}'. Use JPG, PNG, WEBP, or BMP."
    return None


def _default_output(input_path: str, suffix: str) -> str:
    stem = os.path.splitext(input_path)[0]
    return f"{stem}_{suffix}.png"


def remove_background(
    input_path: str,
    output_path: str | None = None,
    model: str = DEFAULT_MODEL,
    alpha_matting: bool = False,
) -> dict:
    """Strip the background from *input_path* and save as PNG with alpha.

    model: key of `MODELS`. Unknown keys fall back to the default.
    alpha_matting: refines wispy edges (hair, fur) at some extra cost.

    Returns {"success": bool, "file_path": str, "error": str}
    """
    err = _validate_source(input_path)
    if err:
        return _fail(err)

    if output_path is None:
        output_path = _default_output(input_path, "nobg")

    try:
        from rembg import new_session, remove as rembg_remove
        from PIL import Image
    except (ImportError, SystemExit) as exc:
        return _fail(f"Background removal unavailable: {exc}")

    session_name = MODELS.get(model, MODELS[DEFAULT_MODEL])[0]

    try:
        session = new_session(session_name)
        with Image.open(input_path) as img:
            result = rembg_remove(
                img,
                session=session,
                alpha_matting=alpha_matting,
                post_process_mask=True,
            )
        result.save(output_path, format="PNG")
    except Exception as exc:
        return _fail(str(exc))

    return {"success": True, "file_path": output_path, "error": ""}


def _mask_from_selection(
    width: int,
    height: int,
    shape: str,
    points: list[tuple[float, float]],
    brush_size: float = 0.04,
):
    """Rasterise a drawn selection into a uint8 mask (255 = selected).

    `points` are fractions of width/height so a selection stays valid if the
    preview was scaled. A brush is a polyline stroked with a round cap; a lasso
    is a filled polygon; a rect uses its first and last point as corners.
    """
    import numpy as np
    import cv2

    mask = np.zeros((height, width), np.uint8)
    if not points:
        return mask

    px = [(int(round(fx * width)), int(round(fy * height))) for fx, fy in points]

    if shape == SHAPE_RECT and len(px) >= 2:
        (x0, y0), (x1, y1) = px[0], px[-1]
        cv2.rectangle(mask, (min(x0, x1), min(y0, y1)),
                      (max(x0, x1), max(y0, y1)), 255, -1)
    elif shape == SHAPE_ELLIPSE and len(px) >= 2:
        # Drag defines the bounding box; the ellipse is inscribed in it.
        (x0, y0), (x1, y1) = px[0], px[-1]
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        ax, ay = max(1, abs(x1 - x0) // 2), max(1, abs(y1 - y0) // 2)
        cv2.ellipse(mask, (cx, cy), (ax, ay), 0, 0, 360, 255, -1)
    elif shape == SHAPE_LASSO and len(px) >= 3:
        cv2.fillPoly(mask, [np.array(px, np.int32)], 255)
    else:
        # Brush — stroke the polyline. Thickness is a fraction of the smaller
        # edge so the same stroke scales with image size.
        thickness = max(1, int(round(brush_size * min(width, height))))
        if len(px) == 1:
            cv2.circle(mask, px[0], max(1, thickness // 2), 255, -1)
        else:
            cv2.polylines(mask, [np.array(px, np.int32)], False, 255,
                          thickness, lineType=cv2.LINE_AA)
    return mask


def sam_available() -> bool:
    """True when SAM's weights are already cached by rembg."""
    try:
        home = os.environ.get("U2NET_HOME") or os.path.join(
            os.path.expanduser("~"), ".u2net")
        enc = os.path.join(home, "sam_vit_b_01ec64.encoder.onnx")
        dec = os.path.join(home, "sam_vit_b_01ec64.decoder.onnx")
        return (os.path.isfile(enc) and os.path.getsize(enc) > 200 * 1024 ** 2
                and os.path.isfile(dec))
    except Exception:
        return False


def download_sam() -> dict:
    """Warm rembg's SAM cache by creating the session, which fetches weights.

    Returns {"success", "error"}. Safe to call when already installed.
    """
    global _sam_session
    try:
        from rembg import new_session
        _sam_session = new_session(SAM_SESSION)
        return {"success": True, "file_path": "", "error": ""}
    except Exception as exc:
        return _fail(f"Could not download the smart-select model: {exc}")


def _subject_component(input_path: str, seed_xy: tuple[int, int],
                       width: int, height: int, model: str | None = None):
    """Whole-subject mask containing *seed_xy*, or None.

    Runs a salient-object segmenter over the image and keeps only the connected
    component the seed lands in, so unrelated subjects elsewhere are ignored.
    Returns None when the seed isn't on a detected subject (a wall, sky, or a
    scene the model finds no subject in) — the caller then keeps SAM's mask.
    """
    global _subject_session, _subject_session_name
    import cv2
    import numpy as np
    from PIL import Image
    from rembg import new_session, remove

    want = _SUBJECT_FOR_MODEL.get(model or "", SUBJECT_SESSION)

    st = os.stat(input_path)
    key = (os.path.abspath(input_path), st.st_mtime_ns, st.st_size, want)
    cached = _subject_cache.get(key)
    if cached is None:
        if _subject_session is None or _subject_session_name != want:
            _subject_session = new_session(want)
            _subject_session_name = want
        with Image.open(input_path) as im:
            out = remove(im.convert("RGB"), session=_subject_session,
                         only_mask=True, post_process_mask=True)
        m = np.array(out.convert("L"))
        if m.shape[:2] != (height, width):
            m = cv2.resize(m, (width, height), interpolation=cv2.INTER_NEAREST)
        binm = (m > 127).astype(np.uint8)
        n, lab = cv2.connectedComponents(binm)
        if len(_subject_cache) > 2:
            _subject_cache.clear()
        _subject_cache[key] = (n, lab)
    else:
        n, lab = cached
    if n <= 1:
        return None
    x = min(max(seed_xy[0], 0), width - 1)
    y = min(max(seed_xy[1], 0), height - 1)
    lid = int(lab[y, x])
    if lid == 0:
        return None
    return (lab == lid).astype(np.uint8) * 255


def _prompt_points(points: list[tuple[float, float]], width: int,
                   height: int, shape: str | None = None
                   ) -> list[tuple[float, float]]:
    """Interior points to prompt segmentation with, in pixels.

    A rect/ellipse stores only its two CORNERS, which sit on the object's edge
    or outright background — prompting with those produced badly oversized masks
    (63.9% of the image instead of the correct 25.7%). Only the centre is used
    for those shapes. A freehand stroke's own points are interior by nature, so
    a few of them are sampled to steady the result.
    """
    if not points:
        return []
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    cx = (min(xs) + max(xs)) / 2 * width
    cy = (min(ys) + max(ys)) / 2 * height

    two_point_shape = shape in (SHAPE_RECT, SHAPE_ELLIPSE) or len(points) == 2
    if two_point_shape:
        return [(cx, cy)]

    out = [(cx, cy)]
    if len(points) >= 5:
        for frac in (0.33, 0.66):
            i = int(len(points) * frac)
            out.append((points[i][0] * width, points[i][1] * height))
    return out


def _smart_mask(input_path: str, width: int, height: int,
                points: list[tuple[float, float]]):
    """Segment the object indicated by *points* and return its mask.

    The drawn shape is only a pointer: its centre (plus a few interior samples
    for a larger scribble) becomes a SAM point prompt, and SAM returns the whole
    object's outline. Measured on a cat photo, a single interior point selected
    the entire animal — ears, body and paws — where GrabCut only refined the
    rectangle it was given.

    Point prompts are used rather than the box prompt rembg also accepts: the
    box path proved unreliable in testing (it caught fragments), while a point
    inside the object was consistently correct.
    """
    global _sam_session
    import numpy as np
    from PIL import Image
    from rembg import new_session, remove

    if _sam_session is None:
        _sam_session = new_session(SAM_SESSION)

    prompt = [{"type": "point", "data": [int(x), int(y)], "label": 1}
              for x, y in _prompt_points(points, width, height)]

    with Image.open(input_path) as img:
        out = remove(img.convert("RGB"), session=_sam_session,
                     sam_prompt=prompt, only_mask=True, post_process_mask=True)
    mask = np.array(out.convert("L"))
    if mask.shape[:2] != (height, width):
        import cv2
        mask = cv2.resize(mask, (width, height), interpolation=cv2.INTER_NEAREST)
    return (mask > 127).astype(np.uint8) * 255


def _sam_embedding(input_path: str):
    """Encoder output for *input_path*, cached (keyed by path + mtime + size)."""
    global _sam_session
    import cv2
    import numpy as np
    from PIL import Image

    st = os.stat(input_path)
    key = (os.path.abspath(input_path), st.st_mtime_ns, st.st_size)
    hit = _sam_embed_cache.get(key)
    if hit is not None:
        return hit

    if _sam_session is None:
        from rembg import new_session
        _sam_session = new_session(SAM_SESSION)

    with Image.open(input_path) as im:
        rgb = np.array(im.convert("RGB"))
    original_size = rgb.shape[:2]

    # Mirror rembg's SamSession.predict preprocessing EXACTLY — it warps into a
    # fixed 684x1024 canvas (not a square), and the decoder's coordinate scaling
    # is derived from that same constant. Guessing 1024x1024 here produced masks
    # that only agreed with rembg at IoU ~0.54.
    input_size = (684, 1024)
    scale = min(input_size[1] / rgb.shape[1], input_size[0] / rgb.shape[0])
    tm = np.array([[scale, 0, 0], [0, scale, 0], [0, 0, 1]], np.float32)
    warped = cv2.warpAffine(rgb, tm[:2], (input_size[1], input_size[0]),
                            flags=cv2.INTER_LINEAR,
                            borderMode=cv2.BORDER_CONSTANT, borderValue=0)

    enc_name = _sam_session.encoder.get_inputs()[0].name
    emb = _sam_session.encoder.run(None, {enc_name: warped.astype(np.float32)})[0]

    payload = {"embedding": emb, "original_size": original_size,
               "transform": tm, "input_size": input_size}
    # Keep only the most recent couple of images — each embedding is ~4 MB.
    if len(_sam_embed_cache) > 2:
        _sam_embed_cache.clear()
    _sam_embed_cache[key] = payload
    return payload


def _sam_decode(input_path: str, points: list[tuple[float, float]],
                width: int, height: int, shape: str | None = None):
    """Decode a mask for *points* using the cached embedding. Fast (~0.1 s)."""
    import cv2
    import numpy as np

    info = _sam_embedding(input_path)
    emb = info["embedding"]
    tm = info["transform"]
    input_size = info["input_size"]

    # rembg scales prompt coords by (new/old) of get_preprocess_shape over the
    # *input_size* canvas, then appends a padding point labelled -1.
    old_h, old_w = input_size
    ratio = 1024.0 / max(old_h, old_w)
    new_h, new_w = int(old_h * ratio + 0.5), int(old_w * ratio + 0.5)

    coords = []
    labels = []
    for px_x, px_y in _prompt_points(points, width, height, shape):
        # Original pixel -> warped canvas -> decoder's expected scale.
        x = px_x * tm[0, 0]
        y = px_y * tm[1, 1]
        coords.append([x * (new_w / old_w), y * (new_h / old_h)])
        labels.append(1)
    coords.append([0.0, 0.0])
    labels.append(-1)          # SAM's padding point

    onnx_coord = np.array(coords, np.float32)[None]
    onnx_label = np.array(labels, np.float32)[None]

    dec = _sam_session.decoder
    names = {i.name for i in dec.get_inputs()}
    feed = {
        "image_embeddings": emb,
        "point_coords": onnx_coord,
        "point_labels": onnx_label,
        "mask_input": np.zeros((1, 1, 256, 256), np.float32),
        "has_mask_input": np.zeros(1, np.float32),
    }
    if "orig_im_size" in names:
        feed["orig_im_size"] = np.array(input_size, np.float32)
    feed = {k: v for k, v in feed.items() if k in names}

    masks = dec.run(None, feed)[0]
    m = masks[0][0]
    # Undo the padding/scale back to the original image size.
    inv = cv2.invertAffineTransform(tm[:2])
    m = (m > 0).astype(np.uint8) * 255
    m = cv2.warpAffine(m, inv, (width, height), flags=cv2.INTER_NEAREST)
    return m


def detect_object_mask(
    input_path: str,
    points: list[tuple[float, float]],
    shape: str | None = None,
    whole_subject: bool = True,
    model: str | None = None,
    sensitivity: str = DEFAULT_SENSITIVITY,
) -> dict:
    """Segment the object indicated by *points* and return its outline.

    Used to PREVIEW a smart selection on the canvas: the caller draws the
    returned contours so the user can see what was detected before committing.

    whole_subject: grow SAM's region into the whole subject it belongs to. Turn
    off to select just the part under the pointer (a sleeve rather than a
    person).
    model: key of `MODELS`; picks the matching subject segmenter so smart select
    follows the quality/speed choice already made for background removal.
    sensitivity: SENS_TIGHT / SENS_BALANCED / SENS_LOOSE — how much completion
    into the surrounding subject is allowed. Tight isolates one of several
    touching people; loose grabs a whole lone subject from a partial hit.

    Returns {"success", "contours", "coverage", "engine", "error"} where
    `contours` is a list of polygons as [(fx, fy), ...] fractions of the image,
    and `coverage` is the fraction of the image the object occupies.
    """
    err = _validate_source(input_path)
    if err:
        return {"success": False, "contours": [], "coverage": 0.0, "error": err}
    if not points:
        return {"success": False, "contours": [], "coverage": 0.0,
                "error": "Nothing to detect."}
    if not sam_available():
        return {"success": False, "contours": [], "coverage": 0.0,
                "error": "Smart-select model is not installed yet."}

    try:
        import cv2
        import numpy as np
        from PIL import Image

        with Image.open(input_path) as img:
            w, h = img.size

        try:
            mask = _sam_decode(input_path, points, w, h, shape)
        except Exception:
            mask = _smart_mask(input_path, w, h, points)
        if mask is None or not mask.any():
            mask = np.zeros((h, w), np.uint8)

        # Complete the selection: SAM tends to return only the region under the
        # pointer (clicking a face gave the facial skin, not the person), so grow
        # it into the whole subject the pointer sits on when one is found.
        engine = "sam"
        # Tight sensitivity deliberately skips completion: SAM's own mask is the
        # single instance under the pointer, which is exactly what isolating one
        # of several touching subjects needs.
        if whole_subject and sensitivity != SENS_TIGHT:
            seed = _prompt_points(points, w, h, shape)[0]
            try:
                comp = _subject_component(input_path, (int(seed[0]), int(seed[1])),
                                          w, h, model)
            except Exception:
                comp = None
            if comp is not None and comp.any():
                sam_area = int((mask > 0).sum())
                comp_area = int((comp > 0).sum())
                overlaps = not mask.any() or ((comp > 0) & (mask > 0)).sum() > 0
                merged = (sensitivity == SENS_BALANCED and sam_area > 0
                          and comp_area > sam_area * _MERGE_RATIO)
                if overlaps and not merged:
                    mask = np.maximum(mask, comp)
                    engine = "subject+sam"
                elif merged:
                    # Keep SAM's instance and tell the caller why, so the UI can
                    # say "one of a group was isolated" instead of silently
                    # differing from loose mode.
                    engine = "sam-isolated"

        if not mask.any():
            return {"success": False, "contours": [], "coverage": 0.0,
                    "error": "No object was detected there."}

        # Keep the exact mask so erase_region can reuse it verbatim.
        mask_key = (os.path.abspath(input_path),
                    tuple((round(x, 5), round(y, 5)) for x, y in points),
                    shape, bool(whole_subject), model or "", sensitivity)
        if len(_detected_masks) > 8:
            _detected_masks.clear()
        _detected_masks[mask_key] = mask.copy()

        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_TC89_KCOS)
        out: list[list[tuple[float, float]]] = []
        for c in cnts:
            if cv2.contourArea(c) < (w * h) * 0.0005:
                continue      # drop specks that would only add visual noise
            # Light simplification only — the overlay must look like the real
            # outline (a bicycle wheel must stay a wheel, not become a disc).
            eps = 0.0005 * cv2.arcLength(c, True)
            c = cv2.approxPolyDP(c, eps, True)
            out.append([(float(p[0][0]) / w, float(p[0][1]) / h) for p in c])

        return {"success": True, "contours": out,
                "coverage": float((mask > 0).mean()), "engine": engine,
                "mask_key": mask_key, "error": ""}
    except Exception as exc:
        return {"success": False, "contours": [], "coverage": 0.0,
                "error": str(exc)}


def _mask_from_strokes(width: int, height: int, strokes: list[dict],
                       input_path: str | None = None,
                       sensitivity: str = DEFAULT_SENSITIVITY):
    """Accumulate every stroke's mask, in order.

    A stroke whose `smart` flag is set is resolved by segmentation instead of
    being rasterised literally: the drawn area selects an object and that
    object's outline joins the mask. Falls back to the drawn shape when the
    segmentation model isn't available.

    A stroke marked ``"subtract": True`` is REMOVED from the mask instead of
    added. Order matters, which is why this is a sequential fold rather than a
    union: paint an object, then shave a corner off it with the negative brush.
    """
    import numpy as np

    mask = np.zeros((height, width), np.uint8)
    for st in strokes or []:
        pts = st.get("points") or []
        if not pts:
            continue
        subtract = bool(st.get("subtract"))
        cached = _detected_masks.get(tuple(st["mask_key"])) if st.get("mask_key") else None
        if cached is not None and cached.shape == (height, width):
            # Exact mask from the preview — pixel-identical to what was shown.
            _apply_part(mask, cached, subtract)
            continue

        detected = st.get("detected")
        if detected:
            # The GUI already segmented this stroke and showed the outline to
            # the user — reuse it verbatim so what was previewed is exactly what
            # gets erased (and we don't pay for inference twice).
            import cv2
            part = np.zeros((height, width), np.uint8)
            for poly in detected:
                if len(poly) >= 3:
                    px = np.array([[int(round(x * width)), int(round(y * height))]
                                   for x, y in poly], np.int32)
                    cv2.fillPoly(part, [px], 255)
        elif st.get("smart") and input_path and sam_available():
            try:
                if sensitivity == SENS_TIGHT:
                    part = _smart_mask(input_path, width, height, pts)
                else:
                    # No preview was cached (Apply without a detect pass), so
                    # redo the same completion the preview would have done —
                    # otherwise Apply and preview disagree.
                    det = detect_object_mask(
                        input_path, pts, st.get("shape"), True, None,
                        sensitivity)
                    key = det.get("mask_key")
                    part = (_detected_masks.get(key) if det.get("success")
                            and key else None)
                    if part is None:
                        part = _smart_mask(input_path, width, height, pts)
            except Exception:
                part = _mask_from_selection(
                    width, height, st.get("shape", SHAPE_BRUSH), pts,
                    st.get("brush", 0.04))
        else:
            part = _mask_from_selection(
                width, height, st.get("shape", SHAPE_BRUSH), pts,
                st.get("brush", 0.04))
        _apply_part(mask, part, subtract)
    return mask


def _apply_part(mask, part, subtract: bool) -> None:
    """Add *part* to *mask*, or cut it out when *subtract*. In place."""
    import numpy as np
    if part is None:
        return
    if subtract:
        mask[part > 0] = 0
    else:
        np.maximum(mask, part, out=mask)


def lama_weights_path() -> str:
    """Where the LaMa ONNX file is cached (may not exist yet)."""
    try:
        from utils.paths import ai_packages_dir
        base = str(ai_packages_dir())
    except Exception:
        base = os.path.join(os.path.expanduser("~"), ".videl")
    return os.path.join(base, "inpaint", _LAMA_FILE)


def lama_available() -> bool:
    """True when the LaMa weights are already on disk."""
    p = lama_weights_path()
    # A truncated download would fail to load; require most of the file.
    return os.path.isfile(p) and os.path.getsize(p) > 150 * 1024 ** 2


def download_lama(progress_cb=None) -> dict:
    """Fetch the LaMa weights, resuming a partial download.

    progress_cb(done_bytes, total_bytes) is called as it streams.
    Returns {"success", "file_path", "error"}.
    """
    dst = lama_weights_path()
    if lama_available():
        return {"success": True, "file_path": dst, "error": ""}
    try:
        from utils.wheel_prefetch import download_resumable, remote_size
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        total = remote_size(_LAMA_URL)
        ok = download_resumable(_LAMA_URL, dst, total=total,
                                progress_cb=progress_cb)
        if not ok:
            return _fail("Could not download the healing model.")
        return {"success": True, "file_path": dst, "error": ""}
    except Exception as exc:
        return _fail(f"Healing model download failed: {exc}")


def _lama_infer(img_bgr, mask):
    """Run LaMa over the masked area and paste the fill back at full resolution.

    Composites STRICTLY inside the mask. Earlier versions feathered the boundary
    and colour-matched the fill to a surrounding ring; both were mistakes. The
    model already reproduces the unmasked area essentially exactly (measured:
    mean delta +0.0 per channel), so those steps only smeared real pixels around
    the hole — the feather alone altered pixels up to 21 levels outside the mask,
    which is the halo that read as a "dark cast". Poisson/seamlessClone is worse
    still: it modified 410 outside pixels and blew out highlights.

    The export is fixed at 512x512. A padded crop is used while the hole is a
    small part of the frame (keeps resolution where it matters); above that the
    whole frame is passed instead, because a crop that is mostly hole leaves the
    model no context to reconstruct from and produced a dark patch with a hard
    rectangular seam.
    """
    global _lama_session
    import cv2
    import numpy as np

    if _lama_session is None:
        import onnxruntime as ort
        providers = ["CPUExecutionProvider"]
        try:
            if "CUDAExecutionProvider" in ort.get_available_providers():
                providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        except Exception:
            pass
        _lama_session = ort.InferenceSession(lama_weights_path(),
                                            providers=providers)

    h, w = mask.shape
    ys, xs = np.nonzero(mask)
    if len(ys) == 0:
        return img_bgr

    y0, y1 = int(ys.min()), int(ys.max()) + 1
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    if (mask > 0).mean() < 0.10:
        pad = max(64, int(0.6 * max(y1 - y0, x1 - x0)))
        side = min(max(y1 - y0, x1 - x0) + 2 * pad, min(h, w))
        cy, cx = (y0 + y1) // 2, (x0 + x1) // 2
        ry0 = max(0, min(cy - side // 2, h - side))
        rx0 = max(0, min(cx - side // 2, w - side))
        ry1, rx1 = ry0 + side, rx0 + side
    else:
        ry0, ry1, rx0, rx1 = 0, h, 0, w

    crop = img_bgr[ry0:ry1, rx0:rx1]
    mcrop = mask[ry0:ry1, rx0:rx1]
    ch, cw = crop.shape[:2]

    img_r = cv2.resize(crop, (_LAMA_INPUT, _LAMA_INPUT), interpolation=cv2.INTER_AREA)
    msk_r = cv2.resize(mcrop, (_LAMA_INPUT, _LAMA_INPUT), interpolation=cv2.INTER_NEAREST)

    rgb = cv2.cvtColor(img_r, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    x_in = np.transpose(rgb, (2, 0, 1))[None]
    m_in = (msk_r > 127).astype(np.float32)[None, None]

    out = _lama_session.run(None, {"image": x_in, "mask": m_in})[0][0]
    out = np.transpose(out, (1, 2, 0))
    if out.max() <= 1.5:      # some exports emit 0..1, others 0..255
        out = out * 255.0
    out = np.clip(out, 0, 255).astype(np.uint8)
    out_bgr = cv2.cvtColor(out, cv2.COLOR_RGB2BGR)
    out_bgr = cv2.resize(out_bgr, (cw, ch), interpolation=cv2.INTER_CUBIC)

    # Strict paste: every pixel outside the mask keeps its original value.
    blended = crop.copy()
    inside = mcrop > 0
    blended[inside] = out_bgr[inside]

    res = img_bgr.copy()
    res[ry0:ry1, rx0:rx1] = blended
    return res


def erase_region(
    input_path: str,
    strokes: list[dict],
    output_path: str | None = None,
    heal: str = HEAL_LAMA,
    grow: int = -1,
    invert: bool = False,
    sensitivity: str = DEFAULT_SENSITIVITY,
) -> dict:
    """Remove whatever the user painted over and heal the gap.

    `strokes` is a list of ``{"shape", "points", "brush"}`` dicts — one per
    painted stroke, so a selection can be built up over several passes and can
    mix brush, lasso and rectangle. Coordinates are fractions of the image.

    Everything outside the selection is left byte-for-byte alone; only the
    painted area is replaced.

    heal:
      HEAL_LAMA  reconstruct texture with the LaMa model (best, ~1.5-2 s).
                 Falls back to the fast fill when the weights aren't present.
      HEAL_FAST  cv2.inpaint diffusion — instant, but visibly blurs texture.
      HEAL_NONE  leave the region transparent.

    invert: erase EVERYTHING EXCEPT the selection — select the one person to
    keep, tick invert, and the rest of the frame goes. Inverting also flips the
    grow direction: the selection is *eroded* rather than dilated, so the kept
    subject's own anti-aliased edge is what gets consumed, not a ring of the
    thing being removed.
    sensitivity: passed through to smart strokes that still need segmenting.

    Returns {"success", "file_path", "error", "heal_used"}.
    """
    err = _validate_source(input_path)
    if err:
        return _fail(err)
    if not strokes:
        return _fail("Draw over what you want removed first.")

    # Accept legacy True/False for the old boolean parameter.
    if heal is True:
        heal = HEAL_LAMA
    elif heal is False:
        heal = HEAL_NONE

    if output_path is None:
        output_path = _default_output(input_path, "erased")

    try:
        import cv2
        import numpy as np
        from PIL import Image
    except ImportError as exc:
        return _fail(f"Erase unavailable: {exc}")

    try:
        with Image.open(input_path) as img:
            rgba = img.convert("RGBA")
            w, h = rgba.size
            arr = np.array(rgba)

        mask = _mask_from_strokes(w, h, strokes, input_path, sensitivity)
        if not mask.any():
            return _fail("The drawn selection was empty.")
        if invert and not (mask == 0).any():
            return _fail("The selection covers the whole image — "
                         "inverting it would leave nothing.")

        if grow < 0:
            # Scale with the image: a fixed few pixels is far too little on a
            # large photo. Measured on a 900px-wide shot, growing 3px left the
            # fill 20 levels off its surroundings because LaMa could still see
            # the object's own dark edge; ~10px brought that to 4. Anti-aliased
            # and slightly-missed edges are the main source of a "dark cast".
            grow = max(4, int(round(0.011 * min(w, h))))
        if grow > 0:
            kernel = cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE, (grow * 2 + 1, grow * 2 + 1))
            # Eroding before the flip == dilating the erased area after it, so
            # both directions push the boundary away from what is being KEPT.
            mask = cv2.erode(mask, kernel) if invert else cv2.dilate(mask, kernel)
            if invert and not mask.any():
                # A thin selection can erode to nothing; keep the original.
                mask = _mask_from_strokes(w, h, strokes, input_path, sensitivity)

        if invert:
            mask = np.where(mask > 0, 0, 255).astype(np.uint8)

        hole_fraction = float((mask > 0).mean())

        smart_wanted = any(st.get("smart") for st in strokes)
        smart_used = smart_wanted and (
            any(st.get("detected") for st in strokes) or sam_available())

        heal_used = heal
        if heal == HEAL_NONE:
            arr[:, :, 3] = np.where(mask > 0, 0, arr[:, :, 3])
            Image.fromarray(arr).save(output_path, format="PNG")
        else:
            bgr = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
            filled = None
            if heal == HEAL_LAMA and lama_available():
                try:
                    filled = _lama_infer(bgr, mask)
                except Exception:
                    filled = None          # fall through to the fast fill
            if filled is None:
                filled = cv2.inpaint(bgr, mask, _HEAL_RADIUS, cv2.INPAINT_TELEA)
                heal_used = HEAL_FAST
            out = cv2.cvtColor(filled, cv2.COLOR_BGR2RGBA)
            out[:, :, 3] = arr[:, :, 3]    # keep any original transparency
            Image.fromarray(out).save(output_path, format="PNG")
    except Exception as exc:
        return _fail(str(exc))

    return {"success": True, "file_path": output_path, "error": "",
            "heal_used": heal_used, "smart_used": smart_used,
            # Callers warn on a large fill: no inpainter can invent a whole
            # background, so a faint outline of the removed subject may remain.
            "hole_fraction": hole_fraction}
