"""View grammar for mcbuilder previews (PLAN rev 7, section 6).

A view is a camera: azimuth (clockwise from north = -Z, degrees) and
elevation (above horizontal, degrees). Views are pure config — parsing and
combining them here has no side effects; rendering happens in preview.py.

Shorthand grammar (ONE separator style — semicolons only):

    "az<ddd>_el<dd>"   e.g. "az045_el025"  (digits in, floats out)
    "orbit<n>_el<dd>"  e.g. "orbit8_el25"  -> n views starting at az000,
                                             stepping +360/n clockwise
    "top"              -> elevation 90 (azimuth degenerate, stored as 0.0)
    "iso"              -> az045_el035 (pinned)

A colon may optionally follow "az"/"orbit"/"el" ("orbit:8_el:25",
"az:045_el:025") — the locked plan's own example (rev 5 §4.5, carried forward) uses the colon style,
so both are accepted and normalize to the same canonical labels.

Malformed tokens raise ViewError naming the offending token.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Hard cap on the number of views in one render set (PLAN rev 7, section 6).
MAX_VIEWS = 36


class ViewError(Exception):
    """A view spec token does not match the grammar, or a view set is invalid."""


@dataclass(frozen=True)
class View:
    azimuth: float  # clockwise from north (-Z), degrees
    elevation: float  # above horizontal, degrees
    label: str  # "az045_el025", "top", "iso"


_GRAMMAR_HELP = (
    "expected one of 'az<ddd>_el<dd>' (e.g. 'az045_el025'), "
    "'orbit<n>_el<dd>' (e.g. 'orbit8_el25'), 'top', or 'iso'; "
    "multiple views are separated by semicolons"
)

_AZ_EL_RE = re.compile(r"^az:?(\d+)_el:?(\d+)$")
_ORBIT_RE = re.compile(r"^orbit:?(\d+)_el:?(\d+)$")


def _fmt_num(value: float) -> str:
    """Format a degree value for a label: integral values zero-padded to 3."""
    rounded = round(value, 3)
    if rounded == int(rounded):
        return str(int(rounded)).zfill(3)
    int_part, _, frac_part = f"{rounded:.3f}".rstrip("0").partition(".")
    return f"{int_part.zfill(3)}.{frac_part}"


def _az_el_label(azimuth: float, elevation: float) -> str:
    return f"az{_fmt_num(azimuth)}_el{_fmt_num(elevation)}"


def _orbit_views(n: int, elevation: float) -> list[View]:
    """n views starting at az000, stepping +360/n clockwise."""
    views = []
    for i in range(n):
        az = (i * 360.0) / n
        # Normalize e.g. 359.9999999 -> 0.0 for float cleanliness.
        az = round(az, 9) % 360.0
        views.append(View(azimuth=az, elevation=elevation,
                          label=_az_el_label(az, elevation)))
    return views


def check_cap(views: list[View]) -> list[View]:
    if len(views) > MAX_VIEWS:
        raise ViewError(
            f"too many views ({len(views)} > {MAX_VIEWS}): an agent will "
            f"request 360 someday; keep it at {MAX_VIEWS} or fewer"
        )
    return views


def _parse_token(token: str) -> list[View]:
    if token == "top":
        return [View(azimuth=0.0, elevation=90.0, label="top")]
    if token == "iso":
        return [View(azimuth=45.0, elevation=35.0, label="iso")]

    m = _AZ_EL_RE.match(token)
    if m:
        az, el = float(m.group(1)), float(m.group(2))
        if not 0.0 <= az < 360.0:
            raise ViewError(
                f"malformed view token {token!r}: azimuth {az} out of range "
                f"[0, 360); {_GRAMMAR_HELP}"
            )
        if not 0.0 <= el <= 90.0:
            raise ViewError(
                f"malformed view token {token!r}: elevation {el} out of range "
                f"[0, 90]; {_GRAMMAR_HELP}"
            )
        return [View(azimuth=az, elevation=el, label=_az_el_label(az, el))]

    m = _ORBIT_RE.match(token)
    if m:
        n, el = int(m.group(1)), float(m.group(2))
        if n < 1:
            raise ViewError(
                f"malformed view token {token!r}: orbit count must be >= 1; "
                f"{_GRAMMAR_HELP}"
            )
        if not 0.0 <= el <= 90.0:
            raise ViewError(
                f"malformed view token {token!r}: elevation {el} out of range "
                f"[0, 90]; {_GRAMMAR_HELP}"
            )
        return _orbit_views(n, el)

    raise ViewError(f"malformed view token {token!r}: {_GRAMMAR_HELP}")


def parse_views(spec: str) -> list[View]:
    """Parse a semicolon-separated view spec into View objects.

    >>> [v.label for v in parse_views("az045_el025;top")]
    ['az045_el025', 'top']
    """
    tokens = [t.strip() for t in spec.split(";")]
    views: list[View] = []
    for token in tokens:
        if not token:
            raise ViewError(
                f"malformed view token {token!r} (empty): {_GRAMMAR_HELP}"
            )
        views.extend(_parse_token(token))
    return check_cap(views)


def default_views() -> list[View]:
    """The default 9-view set: 8-view orbit at 25° elevation + top-down."""
    return parse_views("orbit8_el25;top")


def with_count(views: list[View], n: int) -> list[View]:
    """Append an orbit of n views at 25° elevation to an existing view list.

    n <= 0 -> ValueError. Total views > MAX_VIEWS -> ViewError.
    """
    if n <= 0:
        raise ValueError(f"count must be positive, got {n}")
    combined = list(views) + _orbit_views(n, 25.0)
    return check_cap(combined)


__all__ = [
    "MAX_VIEWS",
    "View",
    "ViewError",
    "default_views",
    "parse_views",
    "with_count",
]
