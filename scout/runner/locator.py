"""Locator — holds annotation data for a UI element.

The generated test.py creates Locator instances with bbox coordinates
and positioning metadata from the annotation session. At runtime,
`center()` computes the viewport coordinates for interaction.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Locator:
    """Annotation-based element locator.

    Parameters
    ----------
    name : str
        Human-readable element name (e.g. "login-button").
    tag : str
        HTML tag (e.g. "button", "input").
    bbox : tuple[int, int, int, int]
        (x, y, width, height) in page coordinates at annotation time.
    scroll_y : int
        Scroll position when the element was annotated.
    pos_type : str
        "abs" (default), "rel", or "dxy".
    parent_element : str | None
        Parent locator name for relative positioning.
    pos_offset : dict | None
        Offset from parent: {"left", "top", "right", "bottom"} or {"dx", "dy"}.
    dynamic : dict | None
        Dynamic dimensions: {"w": int, "h": int}.
    """

    name: str
    tag: str
    bbox: tuple[int, int, int, int]  # (x, y, w, h)
    scroll_y: int = 0
    pos_type: str = "abs"
    parent_element: str | None = None
    pos_offset: dict | None = None
    dynamic: dict | None = None

    def center(self) -> tuple[int, int]:
        """Compute center point in current viewport coordinates.

        For abs positioning: center = (x + w/2, y - scroll_y + h/2).
        Relative and dxy positioning will be expanded in future versions.
        """
        x, y, w, h = self.bbox
        cx = x + w // 2
        cy = (y - self.scroll_y) + h // 2
        return cx, cy

    def __repr__(self) -> str:
        return f"Locator({self.name!r}, tag={self.tag!r}, bbox={self.bbox})"
