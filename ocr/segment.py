"""Cut a Linder-Walberg page scan into strips the OCR model can read.

The scans are 600 dpi bilevel TIFFs (about 3420 x 5215) holding a running head
and two columns of small print. CLLG/Qwen3VL-8B-synth_real was trained on
images with a longest side of 1024 px, and a whole page at that size leaves the
Greek diacritics illegible. So each page is split into its running head and
columns, each column is cut at blank rows into strips, and every strip is
scaled by the same factor and capped at a longest side of 1024 px.

A letter heading such as "B." is centred across both columns, so the body is
first split into sections at anything that crosses the gutter; the reading
order is then section by section, left column before right.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np
from PIL import Image

INK_ROW_FRACTION = 0.002     # a row with less ink than this is blank
GUTTER_INK_FRACTION = 0.02   # a gutter column may cross this much ink
MIN_GUTTER_PX = 20           # narrowest run accepted as the column gutter
SPAN_MERGE_PX = 60           # gutter-crossing ink this close is one element
MIN_SECTION_PX = 120         # thinner sections are folded into a span
MAX_SPAN_PX = 400            # a letter heading is a few lines at most
BREAK_GAP_FACTOR = 2.5       # its blank gap dwarfs the gap between lines
CUT_SEARCH_PX = 220          # how far from an even split a strip cut may move


@dataclass
class Strip:
    kind: str              # "head", "span", "col" or "page"
    section: int           # body section, top to bottom
    column: int            # 0 left, 1 right; -1 when the strip is full width
    index: int             # strip number within its column of the section
    box: tuple[int, int, int, int]   # left, top, right, bottom in the scan

    def __post_init__(self):
        self.box = tuple(int(v) for v in self.box)   # numpy ints are not JSON

    def as_dict(self) -> dict:
        return asdict(self)


def load_grey(path: str) -> Image.Image:
    with Image.open(path) as im:
        return im.convert("L")


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Half-open [start, end) runs of True in a 1-D mask."""
    padded = np.concatenate([[False], mask, [False]])
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    return [(int(s), int(e)) for s, e in zip(edges[::2], edges[1::2])]


def _bbox(ink: np.ndarray) -> tuple[int, int, int, int] | None:
    rows = np.flatnonzero(ink.any(axis=1))
    cols = np.flatnonzero(ink.any(axis=0))
    if rows.size == 0:
        return None
    return int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1


def _blank_rows(ink: np.ndarray) -> np.ndarray:
    return ink.mean(axis=1) <= INK_ROW_FRACTION


def _cut_rows(ink: np.ndarray, top: int, bottom: int, parts: int) -> list[int]:
    """Cut points between top and bottom, each moved to the blankest nearby row."""
    profile = ink[top:bottom].sum(axis=1)
    cuts = [top]
    for k in range(1, parts):
        target = (bottom - top) * k // parts
        lo = max(target - CUT_SEARCH_PX, 1)
        hi = min(target + CUT_SEARCH_PX, bottom - top - 1)
        window = profile[lo:hi]
        # Prefer the middle of the widest stretch of minimal ink.
        quiet = window <= window.min()
        start, end = max(_runs(quiet), key=lambda r: (r[1] - r[0], -abs((r[0] + r[1]) // 2 + lo - target)))
        cuts.append(top + lo + (start + end) // 2)
    cuts.append(bottom)
    return cuts


def _find_gutter(body: np.ndarray) -> tuple[int, int] | None:
    """The widest nearly blank run of columns in the middle of the body.

    The top tenth is skipped, since an undetected running head spans the
    gutter, and a little ink is tolerated for letter headings and specks.
    """
    col_blank = body[body.shape[0] // 10:].mean(axis=0) <= GUTTER_INK_FRACTION
    mid_lo, mid_hi = int(0.3 * body.shape[1]), int(0.7 * body.shape[1])
    gutters = [(s, e) for s, e in _runs(col_blank) if s >= mid_lo and e <= mid_hi and e - s >= MIN_GUTTER_PX]
    return max(gutters, key=lambda r: r[1] - r[0]) if gutters else None


def _spans(ink: np.ndarray, top: int, bottom: int, gs: int, ge: int) -> list[tuple[int, int]]:
    """Row ranges of elements that cross the gutter, grown to blank rows."""
    core = ink[top:bottom, gs + (ge - gs) // 4: ge - (ge - gs) // 4]
    hits = np.flatnonzero(core.any(axis=1))
    if hits.size == 0:
        return []
    groups, start, prev = [], hits[0], hits[0]
    for r in hits[1:]:
        if r - prev > SPAN_MERGE_PX:
            groups.append((start, prev + 1))
            start = r
        prev = r
    groups.append((start, prev + 1))

    blank = _blank_rows(ink[top:bottom])
    line_gap = float(np.median([e - s for s, e in _runs(blank)] or [0]))
    spans = []
    for s, e in groups:
        while s > 0 and not blank[s - 1]:
            s -= 1
        while e < len(blank) and not blank[e]:
            e += 1
        gap_above = s - max((r for r in np.flatnonzero(~blank[:s])), default=-1) - 1
        gap_below = (np.flatnonzero(~blank[e:])[:1].tolist() or [len(blank) - e])[0]
        if e - s > MAX_SPAN_PX or max(gap_above, gap_below) < BREAK_GAP_FACTOR * line_gap:
            continue   # a speck or skewed line in the gutter, not a heading
        if spans and s - spans[-1][1] < MIN_SECTION_PX:
            spans[-1] = (spans[-1][0], e)
        else:
            spans.append((s, e))
    return [(top + s, top + e) for s, e in spans]


def _column_strips(ink, section, ci, kind, cl, cr, top, bottom, scale, max_side) -> list[Strip]:
    box = _bbox(ink[top:bottom, cl:cr])
    if box is None:
        return []
    cl, ct, cr, cb = cl + box[0], top + box[1], cl + box[2], top + box[3]
    parts = max(1, math.ceil((cb - ct) * scale / max_side))
    cuts = _cut_rows(ink[:, cl:cr], ct, cb, parts)
    return [Strip(kind, section, ci, si, (cl, cuts[si], cr, cuts[si + 1])) for si in range(parts)]


def segment(grey: Image.Image, scale: float, max_side: int, columns: bool = True) -> list[Strip]:
    """Strips in reading order; columns=False reads the page as one column."""
    ink = np.asarray(grey) < 128
    h, _ = ink.shape
    page_box = _bbox(ink)
    if page_box is None:
        return []
    left, top, right, bottom = page_box

    # Running head: the first band of text, if a gap clearly wider than the
    # line spacing separates it from the body.
    row_has_ink = ~_blank_rows(ink[:, left:right])
    bands = [(s, e) for s, e in _runs(row_has_ink) if e - s > 8]
    strips: list[Strip] = []
    body_top = top
    if len(bands) > 3:
        gaps = [bands[i + 1][0] - bands[i][1] for i in range(len(bands) - 1)]
        hs, he = bands[0]
        head_box = _bbox(ink[hs:he, left:right])
        margin = 0.05 * (right - left)
        # A running head carries the page number at one margin; a centred
        # letter heading such as "A." touches neither.
        at_margin = head_box is not None and (head_box[0] < margin or head_box[2] > right - left - margin)
        if gaps[0] > 2.0 * float(np.median(gaps)) and he - hs < 0.04 * h and at_margin:
            strips.append(Strip("head", -1, -1, 0, (left, bands[0][0], right, bands[0][1])))
            body_top = bands[1][0]

    if not columns:
        return strips + _column_strips(ink, 0, -1, "page", left, right, body_top, bottom, scale, max_side)
    gutter = _find_gutter(ink[body_top:bottom, left:right])
    if gutter is not None:
        return strips + _two_column(ink, 0, left, right, body_top, bottom, gutter, scale, max_side)

    # No gutter across the whole body: the columns may shift at a mid-page
    # heading or table, so split at wide blank gaps and lay out each block.
    blank = _blank_rows(ink[body_top:bottom, left:right])
    gap_runs = _runs(blank)
    line_gap = float(np.median([e - s for s, e in gap_runs] or [0]))
    cuts = [body_top] + [body_top + (s + e) // 2 for s, e in gap_runs
                         if e - s >= BREAK_GAP_FACTOR * line_gap] + [bottom]
    section = 0
    for bt, bb in zip(cuts, cuts[1:]):
        if not ink[bt:bb, left:right].any():
            continue
        gutter = _find_gutter(ink[bt:bb, left:right]) if bb - bt >= MIN_SECTION_PX else None
        if gutter is not None:
            block = _two_column(ink, section, left, right, bt, bb, gutter, scale, max_side)
        else:
            block = _column_strips(ink, section, -1, "page", left, right, bt, bb, scale, max_side)
        strips += block
        section = max(s.section for s in block) + 1
    return strips


def _two_column(ink, section, left, right, top, bottom, gutter, scale, max_side) -> list[Strip]:
    """Two-column sections alternating with the full-width spans between them."""
    gs, ge = left + gutter[0], left + gutter[1]
    strips: list[Strip] = []
    cursor = top
    for ss, se in _spans(ink, top, bottom, gs, ge) + [(bottom, bottom)]:
        if ss - cursor >= MIN_SECTION_PX:
            for ci, (cl, cr) in enumerate([(left, gs), (ge, right)]):
                strips += _column_strips(ink, section, ci, "col", cl, cr, cursor, ss, scale, max_side)
            section += 1
        elif ss > cursor:
            ss = cursor   # a sliver above the span belongs to it
        if se > ss:
            strips += _column_strips(ink, section, -1, "span", left, right, ss, se, scale, max_side)
            section += 1
        cursor = se
    return strips


def render(grey: Image.Image, strip: Strip, scale: float, max_side: int, pad: int = 12) -> Image.Image:
    """Crop a strip with a white margin, scale it, and cap its longest side."""
    l, t, r, b = strip.box
    crop = grey.crop((max(l - pad, 0), max(t - pad, 0), min(r + pad, grey.width), min(b + pad, grey.height)))
    factor = min(scale, max_side / max(crop.size))
    size = (max(1, round(crop.width * factor)), max(1, round(crop.height * factor)))
    return crop.resize(size, Image.LANCZOS).convert("RGB")
