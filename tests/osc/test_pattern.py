"""OSC address patterns, matched against incoming addresses, one capture per wildcard."""

import pytest

from haybale_protokol_osc.pattern import compile_pattern


def test_star_captures() -> None:
    pattern = compile_pattern("/tracker/blob/*/pos")
    assert pattern.captures == 1
    assert pattern.match("/tracker/blob/3/pos") == ("3",)
    assert pattern.match("/tracker/blob/3/size") is None


def test_star_does_not_cross_slash() -> None:
    assert compile_pattern("/a/*").match("/a/b/c") is None
    assert compile_pattern("/a/*").match("/a/") == ("",)


def test_question_and_range() -> None:
    pattern = compile_pattern("/ch?/[0-9]")
    assert pattern.captures == 2
    assert pattern.match("/chA/7") == ("A", "7")
    assert pattern.match("/chAB/7") is None


def test_negated_range() -> None:
    pattern = compile_pattern("/x/[!a-c]")
    assert pattern.match("/x/d") == ("d",)
    assert pattern.match("/x/b") is None


def test_negated_range_never_matches_slash() -> None:
    pattern = compile_pattern("/x[!a]y")
    assert pattern.match("/x/y") is None
    assert pattern.match("/xby") == ("b",)


def test_alternatives() -> None:
    pattern = compile_pattern("/{left,right}/gain")
    assert pattern.match("/left/gain") == ("left",)
    assert pattern.match("/up/gain") is None


def test_special_characters_are_literal() -> None:
    assert compile_pattern("/a.b+c").match("/a.b+c") == ()
    assert compile_pattern("/a.b+c").match("/aXb+c") is None


def test_exact_is_exact() -> None:
    pattern = compile_pattern("/fader/1")
    assert pattern.is_exact
    assert pattern.captures == 0
    assert pattern.match("/fader/1") == ()
    assert pattern.match("/fader/10") is None
    assert not compile_pattern("/fader/*").is_exact


def test_empty_matches_all() -> None:
    pattern = compile_pattern("")
    assert not pattern.is_exact
    assert pattern.match("/anything/at/all") == ()


@pytest.mark.parametrize("text", ["/a/[0-9", "/a/{x,y", "/a/}", "/a/]", "no-slash"])
def test_invalid_pattern_raises(text: str) -> None:
    with pytest.raises(ValueError, match="position|start"):
        compile_pattern(text)


@pytest.mark.parametrize("text", ["/a[]", "/a[z-a]", "/a[!]"])
def test_bad_ranges_raise_value_error(text: str) -> None:
    with pytest.raises(ValueError, match="position"):
        compile_pattern(text)
