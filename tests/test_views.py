"""Grammar tests for mcbuilder.views (PLAN section 4.4)."""

import pytest

from mcbuilder.views import (
    MAX_VIEWS,
    View,
    ViewError,
    default_views,
    parse_views,
    with_count,
)


def test_az_el_shorthand():
    (v,) = parse_views("az045_el025")
    assert v == View(azimuth=45.0, elevation=25.0, label="az045_el025")


def test_az_el_zero_padded_in_floats_out():
    (v,) = parse_views("az000_el090")
    assert v.azimuth == 0.0 and v.elevation == 90.0
    assert isinstance(v.azimuth, float) and isinstance(v.elevation, float)


def test_iso_is_pinned():
    (v,) = parse_views("iso")
    assert (v.azimuth, v.elevation, v.label) == (45.0, 35.0, "iso")


def test_top():
    (v,) = parse_views("top")
    assert (v.azimuth, v.elevation, v.label) == (0.0, 90.0, "top")


def test_orbit_math():
    views = parse_views("orbit8_el25")
    assert len(views) == 8
    assert [v.azimuth for v in views] == [0.0, 45.0, 90.0, 135.0,
                                          180.0, 225.0, 270.0, 315.0]
    assert all(v.elevation == 25.0 for v in views)
    assert views[0].label == "az000_el025"
    assert views[3].label == "az135_el025"
    assert views[7].label == "az315_el025"


def test_orbit_single():
    (v,) = parse_views("orbit1_el10")
    assert (v.azimuth, v.elevation) == (0.0, 10.0)


def test_semicolon_separated():
    views = parse_views("az045_el025;top;iso")
    assert [v.label for v in views] == ["az045_el025", "top", "iso"]


def test_whitespace_tolerated():
    views = parse_views("  az045_el025 ; top ")
    assert [v.label for v in views] == ["az045_el025", "top"]


@pytest.mark.parametrize("bad", [
    "az45_el25x",      # trailing junk
    "az_el25",         # missing digits
    "az045el025",      # missing underscore
    "az045_el",        # missing elevation
    "orbit_el25",      # missing count
    "orbit0_el25",     # zero count
    "iso2",            # unknown word
    "bottom",          # unknown word
    "az045_el025,top",  # comma is not a separator (ONE separator style)
    "",                # empty spec
    "az045_el025;",    # trailing empty token
    "az999_el025",     # azimuth out of range
    "az045_el91",      # elevation out of range
])
def test_malformed_tokens_raise_with_token_named(bad):
    with pytest.raises(ViewError) as exc_info:
        parse_views(bad)
    msg = str(exc_info.value)
    # The offending token (or its first piece) must be named in the message.
    first_token = bad.split(";")[0].split(",")[0] or bad
    assert first_token in msg or repr(first_token) in msg


def test_view_error_is_exception_subclass():
    assert issubclass(ViewError, Exception)


def test_orbit_over_cap_raises():
    with pytest.raises(ViewError):
        parse_views(f"orbit{MAX_VIEWS + 1}_el25")


def test_exactly_cap_is_fine():
    assert len(parse_views(f"orbit{MAX_VIEWS}_el25")) == MAX_VIEWS


def test_default_views_is_nine():
    views = default_views()
    assert len(views) == 9
    assert [v.label for v in views] == [
        "az000_el025", "az045_el025", "az090_el025", "az135_el025",
        "az180_el025", "az225_el025", "az270_el025", "az315_el025",
        "top",
    ]
    assert all(v.elevation == 25.0 for v in views[:8])
    assert views[8].elevation == 90.0


def test_with_count_appends_orbit():
    base = parse_views("top")
    out = with_count(base, 4)
    assert [v.label for v in out] == [
        "top", "az000_el025", "az090_el025", "az180_el025", "az270_el025",
    ]
    # Input list is not mutated.
    assert [v.label for v in base] == ["top"]


def test_with_count_nonpositive_raises_valueerror():
    with pytest.raises(ValueError):
        with_count([], 0)
    with pytest.raises(ValueError):
        with_count([], -3)


def test_with_count_over_cap_raises_viewerror():
    base = parse_views(f"orbit{MAX_VIEWS}_el25")
    with pytest.raises(ViewError):
        with_count(base, 1)
    # But appending within the cap is fine.
    base2 = parse_views(f"orbit{MAX_VIEWS - 2}_el25")
    assert len(with_count(base2, 2)) == MAX_VIEWS
