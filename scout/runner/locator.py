"""Locator — encapsulates annotation data and coordinate resolution logic.

A Locator holds the annotation-time bbox plus positioning metadata (abs/rel/dxy),
and resolves to actual viewport coordinates at runtime. Resolution may involve:
- Parent locator lookups (for rel/dxy positioning)
- Dynamic DOM probing (for elements that change size)
- Filter narrowing (XPath/CSS selector to find specific child elements)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Page as PwPage

log = logging.getLogger(__name__)

# Tolerances for dynamic resolution (px)
_POS_TOLERANCE = 30
_DIM_TOLERANCE = 60
_FILTER_POS_TOLERANCE = 20


class Locator:
    """Annotation-based element locator with runtime coordinate resolution.

    Parameters
    ----------
    name : str
        Human-readable element name (e.g. "login-button").
    tag : str
        HTML tag (e.g. "button", "input").
    bbox : tuple[int, int, int, int]
        (x, y, width, height) in page coordinates at annotation time.
    scroll_y : int
        Page scroll position when the element was annotated.
    pos_type : str
        "abs" (absolute), "rel" (relative to parent), or "dxy" (delta from parent).
    parent : str | None
        Parent locator name for rel/dxy positioning.
    pos_offset : dict | None
        Offset from parent: {"left", "top"} / {"right", "bottom"} for rel,
        or {"dx", "dy"} for dxy.
    dynamic : dict | None
        Dynamic dimension flags: {"w": bool, "h": bool}.
    filter : str | None
        XPath or CSS selector to narrow bbox to a matched child element.
    """

    __slots__ = (
        "_resolved_bbox",
        "bbox",
        "dynamic",
        "filter",
        "name",
        "parent",
        "pos_offset",
        "pos_type",
        "scroll_y",
        "tag",
    )

    def __init__(
        self,
        *,
        name: str,
        tag: str,
        bbox: tuple[int, int, int, int],
        scroll_y: int = 0,
        pos_type: str = "abs",
        parent: str | None = None,
        pos_offset: dict | None = None,
        dynamic: dict | None = None,
        filter: str | None = None,  # noqa: A002
    ) -> None:
        self.name = name
        self.tag = tag
        self.bbox = bbox
        self.scroll_y = scroll_y
        self.pos_type = pos_type
        self.parent = parent
        self.pos_offset = pos_offset or {}
        self.dynamic = dynamic
        self.filter = filter
        self._resolved_bbox: dict[str, int] | None = None

    # ── Static resolution (no page needed) ───────────────────────────────────

    def resolve_static(self, registry: dict[str, Locator]) -> dict[str, int]:
        """Resolve bbox using only annotation data (no runtime DOM access).

        For abs: returns stored bbox directly.
        For rel/dxy: computes from parent's resolved bbox.
        """
        x, y, w, h = self.bbox

        if self.pos_type == "abs":
            self._resolved_bbox = {"x": x, "y": y, "w": w, "h": h}

        elif self.pos_type == "dxy":
            parent_bbox = self._get_parent_bbox(registry)
            if parent_bbox is None:
                log.warning(
                    "dxy locator %r: parent %r not resolved, using raw bbox",
                    self.name,
                    self.parent,
                )
                self._resolved_bbox = {"x": x, "y": y, "w": w, "h": h}
            else:
                dx = self.pos_offset.get("dx", 0)
                dy = self.pos_offset.get("dy", 0)
                self._resolved_bbox = {
                    "x": parent_bbox["x"] + dx,
                    "y": parent_bbox["y"] + dy,
                    "w": w,
                    "h": h,
                }

        elif self.pos_type == "rel":
            parent_bbox = self._get_parent_bbox(registry)
            if parent_bbox is None:
                log.warning(
                    "rel locator %r: parent %r not resolved, using raw bbox",
                    self.name,
                    self.parent,
                )
                self._resolved_bbox = {"x": x, "y": y, "w": w, "h": h}
            else:
                rx = self._resolve_rel_x(parent_bbox, w)
                ry = self._resolve_rel_y(parent_bbox, h)
                self._resolved_bbox = {"x": rx, "y": ry, "w": w, "h": h}
        else:
            self._resolved_bbox = {"x": x, "y": y, "w": w, "h": h}

        return self._resolved_bbox

    def _get_parent_bbox(self, registry: dict[str, Locator]) -> dict[str, int] | None:
        if not self.parent:
            return None
        parent_loc = registry.get(self.parent)
        if parent_loc is None:
            return None
        if parent_loc._resolved_bbox is None:
            parent_loc.resolve_static(registry)
        return parent_loc._resolved_bbox

    def _resolve_rel_x(self, parent_bbox: dict[str, int], w: int) -> int:
        if "left" in self.pos_offset:
            return parent_bbox["x"] + self.pos_offset["left"]
        elif "right" in self.pos_offset:
            return parent_bbox["x"] + parent_bbox["w"] - self.pos_offset["right"] - w
        return parent_bbox["x"]

    def _resolve_rel_y(self, parent_bbox: dict[str, int], h: int) -> int:
        if "top" in self.pos_offset:
            return parent_bbox["y"] + self.pos_offset["top"]
        elif "bottom" in self.pos_offset:
            return parent_bbox["y"] + parent_bbox["h"] - self.pos_offset["bottom"] - h
        return parent_bbox["y"]

    # ── Dynamic resolution (needs Playwright page) ───────────────────────────

    async def resolve(self, page: PwPage, registry: dict[str, Locator]) -> dict[str, int]:
        """Full resolution: static → dynamic resize → filter narrowing.

        Call this at runtime before interacting with the element.
        """
        # Step 1: static resolution
        self.resolve_static(registry)
        if self._resolved_bbox is None:
            msg = f"resolve_static() failed for {self.name!r}"
            raise RuntimeError(msg)

        # Step 2: dynamic resize (re-measure from DOM if flagged)
        if self.pos_type == "abs" and self.dynamic:
            dyn_w = bool(self.dynamic.get("w"))
            dyn_h = bool(self.dynamic.get("h"))
            if dyn_w or dyn_h:
                actual = await self._probe_dynamic(page, dyn_w, dyn_h)
                if actual:
                    log.info(
                        "Dynamic resize: %s → %dx%d (was %dx%d)",
                        self.name,
                        actual["w"],
                        actual["h"],
                        self._resolved_bbox["w"],
                        self._resolved_bbox["h"],
                    )
                    self._resolved_bbox = actual

        # Step 2b: re-resolve rel/dxy children whose parents may have changed
        for loc in registry.values():
            if loc.parent and loc.pos_type in ("rel", "dxy"):
                parent = registry.get(loc.parent)
                if parent and parent._resolved_bbox:
                    loc.resolve_static(registry)

        # Step 3: filter narrowing (XPath/CSS selector)
        if self.filter:
            filtered = await self._apply_filter(page)
            if filtered:
                log.info(
                    "Filter applied: %s [%s] → bbox(%d,%d %dx%d)",
                    self.name,
                    self.filter,
                    filtered["x"],
                    filtered["y"],
                    filtered["w"],
                    filtered["h"],
                )
                self._resolved_bbox = filtered

        return self._resolved_bbox

    async def _probe_dynamic(
        self, page: PwPage, dyn_w: bool, dyn_h: bool
    ) -> dict[str, int] | None:
        """Probe DOM near stored position to find actual element dimensions."""
        bb = self._resolved_bbox
        if bb is None:
            return None

        return await page.evaluate(
            """({origX, origY, origW, origH, dynW, dynH, POS_T, DIM_T}) => {
                function isFixed(node) {
                    while (node && node !== document.documentElement) {
                        if (getComputedStyle(node).position === 'fixed') return true;
                        node = node.parentElement;
                    }
                    return false;
                }
                function walkAndMatch(startEl) {
                    let best = null;
                    let bestFallback = null;
                    let el = startEl;
                    while (el && el !== document.documentElement) {
                        const r = el.getBoundingClientRect();
                        const fixed = isFixed(el);
                        const ex = Math.round(r.left + (fixed ? 0 : window.scrollX));
                        const ey = Math.round(r.top  + (fixed ? 0 : window.scrollY));
                        const ew = Math.round(r.width);
                        const eh = Math.round(r.height);
                        const posOk = Math.abs(ex - origX) <= POS_T
                                   && Math.abs(ey - origY) <= POS_T;
                        const wOk = dynW || Math.abs(ew - origW) <= DIM_T;
                        const hOk = dynH || Math.abs(eh - origH) <= DIM_T;
                        if (posOk && wOk && hOk) {
                            const candidate = {
                                x: dynW ? ex : origX,
                                y: dynH ? ey : origY,
                                w: dynW ? ew : origW,
                                h: dynH ? eh : origH,
                            };
                            const dynDim = dynH ? eh : (dynW ? ew : 0);
                            const origDim = dynH ? origH : (dynW ? origW : 0);
                            if (dynDim >= origDim) {
                                const bestDim = dynH ? (best?.h ?? Infinity)
                                                     : (best?.w ?? Infinity);
                                if (dynDim < bestDim) best = candidate;
                            } else {
                                const fbDim = dynH ? (bestFallback?.h ?? 0)
                                                   : (bestFallback?.w ?? 0);
                                if (dynDim > fbDim) bestFallback = candidate;
                            }
                        }
                        el = el.parentElement;
                    }
                    return best || bestFallback;
                }
                const probes = [
                    { vx: origX + origW / 2 - window.scrollX,
                      vy: origY + 10 - window.scrollY },
                    { vx: origX + origW / 2,
                      vy: origY + 10 },
                ];
                for (const { vx, vy } of probes) {
                    if (vx < 0 || vy < 0 || vx > window.innerWidth
                        || vy > window.innerHeight) continue;
                    const el = document.elementFromPoint(vx, vy);
                    if (!el) continue;
                    const result = walkAndMatch(el);
                    if (result) return result;
                }
                return null;
            }""",
            {
                "origX": bb["x"],
                "origY": bb["y"],
                "origW": bb["w"],
                "origH": bb["h"],
                "dynW": dyn_w,
                "dynH": dyn_h,
                "POS_T": _POS_TOLERANCE,
                "DIM_T": _DIM_TOLERANCE,
            },
        )

    async def _apply_filter(self, page: PwPage) -> dict[str, int] | None:
        """Apply XPath/CSS filter to narrow bbox to a specific child element."""
        bb = self._resolved_bbox
        if bb is None:
            return None

        return await page.evaluate(
            """({filter, bx, by, bw, bh, POS_T}) => {
                const vx = bx + bw / 2 - window.scrollX;
                const vy = by + bh / 2 - window.scrollY;
                if (vx < 0 || vy < 0 || vx > window.innerWidth
                    || vy > window.innerHeight) return null;
                let container = document.elementFromPoint(vx, vy);
                if (!container) return null;
                while (container && container !== document.documentElement) {
                    const r = container.getBoundingClientRect();
                    const cx = Math.round(r.left + window.scrollX);
                    const cy = Math.round(r.top  + window.scrollY);
                    const cw = Math.round(r.width);
                    const ch = Math.round(r.height);
                    if (cx <= bx + POS_T && cy <= by + POS_T &&
                        cx + cw >= bx + bw - POS_T &&
                        cy + ch >= by + bh - POS_T) break;
                    container = container.parentElement;
                }
                if (!container || container === document.documentElement) return null;
                let matched = null;
                try {
                    const xr = document.evaluate(filter, container, null,
                        XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                    matched = xr.singleNodeValue;
                } catch (_) {}
                if (!matched) {
                    try { matched = container.querySelector(filter); } catch (_) {}
                }
                if (!matched) return null;
                const mr = matched.getBoundingClientRect();
                return {
                    x: Math.round(mr.left + window.scrollX),
                    y: Math.round(mr.top  + window.scrollY),
                    w: Math.round(mr.width),
                    h: Math.round(mr.height),
                };
            }""",
            {
                "filter": self.filter,
                "bx": bb["x"],
                "by": bb["y"],
                "bw": bb["w"],
                "bh": bb["h"],
                "POS_T": _FILTER_POS_TOLERANCE,
            },
        )

    # ── Coordinate accessors ─────────────────────────────────────────────────

    def center(self) -> tuple[int, int]:
        """Return center of resolved bbox in viewport coordinates.

        If resolve() hasn't been called yet, falls back to static bbox
        adjusted for scroll position.
        """
        if self._resolved_bbox is not None:
            bb = self._resolved_bbox
            cx = bb["x"] + bb["w"] // 2
            cy = bb["y"] + bb["h"] // 2
        else:
            x, y, w, h = self.bbox
            cx = x + w // 2
            cy = y + h // 2

        # Adjust for scroll position (annotation-time scroll → viewport)
        return cx, cy - self.scroll_y

    @property
    def resolved(self) -> bool:
        """Whether this locator has been resolved."""
        return self._resolved_bbox is not None

    def __repr__(self) -> str:
        suffix = ""
        if self.pos_type != "abs":
            suffix = f", pos_type={self.pos_type!r}, parent={self.parent!r}"
        return f"Locator({self.name!r}, tag={self.tag!r}, bbox={self.bbox}{suffix})"
