"""Tests for mcbuilder.blocks: parse, canonicalize, suggest."""

import pytest

from mcbuilder.blocks import canonicalize, parse, suggest


# -- parse ------------------------------------------------------------


def test_parse_bare_name():
    assert parse("minecraft:stone") == ("minecraft:stone", {}, None)


def test_parse_props():
    name, props, nbt = parse("minecraft:oak_stairs[facing=north,half=bottom]")
    assert name == "minecraft:oak_stairs"
    assert props == {"facing": "north", "half": "bottom"}
    assert nbt is None


def test_parse_nbt_only():
    name, props, nbt = parse('minecraft:chest{Items:[{Slot:0b,id:"minecraft:stone"}]}')
    assert name == "minecraft:chest"
    assert props == {}
    assert nbt == '{Items:[{Slot:0b,id:"minecraft:stone"}]}'


def test_parse_props_and_nbt():
    name, props, nbt = parse("minecraft:furnace[facing=east]{BurnTime:200s}")
    assert (name, props, nbt) == ("minecraft:furnace", {"facing": "east"}, "{BurnTime:200s}")


def test_parse_contract_example():
    name, props, nbt = parse("minecraft:oak_stairs[facing=north,half=bottom]{Items:[]}")
    assert name == "minecraft:oak_stairs"
    assert props == {"facing": "north", "half": "bottom"}
    assert nbt == "{Items:[]}"


def test_parse_nbt_with_brackets_inside():
    # '[' inside NBT must not be mistaken for a properties section.
    name, props, nbt = parse('minecraft:chest{Items:[{id:"x"},{id:"y"}]}')
    assert name == "minecraft:chest"
    assert props == {}
    assert nbt == '{Items:[{id:"x"},{id:"y"}]}'


def test_parse_whitespace_around_props_tolerated():
    name, props, _ = parse("minecraft:oak_stairs[ facing = north , half = bottom ]")
    assert props == {"facing": "north", "half": "bottom"}


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "minecraft:stone[",  # unclosed props
        "minecraft:stone[facing=north",  # unclosed props
        "minecraft:stone]",  # stray bracket in name
        "[facing=north]",  # empty name
        "minecraft:stone[]",  # empty property list
        "minecraft:stone[facing]",  # missing '='
        "minecraft:stone[=north]",  # empty key
        "minecraft:stone[facing=]",  # empty value
        "minecraft:stone[facing=north,]",  # trailing comma
        "minecraft:stone[facing=north,facing=south]",  # duplicate key
        "minecraft:stone{a:1",  # unbalanced NBT
        "minecraft:stone{a:'x}",  # unterminated NBT string
        "minecraft:stone{a:1}}",  # unbalanced NBT
        "minecraft:stone{a:1}[x=1]",  # NBT before props
        "minecraft:stone{a:1}{b:2}",  # trailing compound
        "minecraft:stone bar",  # whitespace in name
    ],
)
def test_parse_malformed(bad):
    with pytest.raises(ValueError):
        parse(bad)


# -- canonicalize ------------------------------------------------------


def test_canonicalize_sorts_props():
    assert (
        canonicalize("minecraft:oak_stairs[half=bottom,facing=north]")
        == "minecraft:oak_stairs[facing=north,half=bottom]"
    )


def test_canonicalize_bare_name_unchanged():
    assert canonicalize("minecraft:stone") == "minecraft:stone"


def test_canonicalize_idempotent():
    once = canonicalize("minecraft:oak_stairs[half=bottom,facing=north]{z:1,a:2}")
    assert once == "minecraft:oak_stairs[facing=north,half=bottom]{a:2,z:1}"
    assert canonicalize(once) == once


def test_canonicalize_sorts_nbt_top_level_keys_only():
    # Nested compounds keep their internal order/formatting (values opaque).
    out = canonicalize('minecraft:chest{Lock:"x",Items:[{Slot:0b,id:"minecraft:stone"}]}')
    assert out == 'minecraft:chest{Items:[{Slot:0b,id:"minecraft:stone"}],Lock:"x"}'
    assert canonicalize(out) == out


def test_canonicalize_nbt_nested_untouched():
    out = canonicalize("minecraft:chest{z:1,a:{y:2,b:1}}")
    assert out == "minecraft:chest{a:{y:2,b:1},z:1}"


def test_canonicalize_empty_nbt_compound():
    assert canonicalize("minecraft:chest{}") == "minecraft:chest{}"


def test_canonicalize_quoted_colon_in_string():
    out = canonicalize('minecraft:sign{Text1:"{\\"text\\": \\"a:b\\"}"}')
    assert canonicalize(out) == out


def test_canonicalize_malformed_raises():
    with pytest.raises(ValueError):
        canonicalize("minecraft:stone[facing]")


# -- suggest ------------------------------------------------------------


def test_suggest_close_match():
    cands = ["minecraft:oak_stairs", "minecraft:oak_slab", "minecraft:stone"]
    assert suggest("minecraft:oak_stair", cands)[0] == "minecraft:oak_stairs"


def test_suggest_strips_namespace_for_matching_but_returns_full():
    assert suggest("oak_stairs", ["minecraft:oak_stairs"]) == ["minecraft:oak_stairs"]


def test_suggest_respects_n():
    cands = ["minecraft:stone", "minecraft:stone_bricks", "minecraft:cobblestone"]
    assert len(suggest("minecraft:ston", cands, n=1)) == 1


def test_suggest_no_match_returns_empty():
    assert suggest("zzz_qqq", ["minecraft:stone"]) == []
