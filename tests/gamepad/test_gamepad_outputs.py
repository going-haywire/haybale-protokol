"""Gamepad outputs: names, which messages change them, dead zone and which way is up."""

import math

import pytest

import haybale_protokol_gamepad.gamepad_messages as gm
from haybale_protokol_gamepad.gamepad_outputs import (
    BY_NAME,
    CHOICES,
    Shaping,
    changes,
    is_event,
    selected,
    stick,
    unknown,
    value,
)

RAW = Shaping(dead_zone=0.0, y_up=False)
AXES = (0.6, 0.8, 0.0, 0.0, 0.25, 1.0)
BUTTONS = tuple(i in (0, 11, 14) for i in range(len(gm.BUTTONS)))  # a, d-pad up and right held


def test_every_output_has_a_label_and_a_unique_name() -> None:
    names = [output.name for output in BY_NAME.values()]
    assert len(names) == len(set(names)) == len(CHOICES)
    assert names[:9] == [
        "left_stick_vec",
        "left_stick_x",
        "left_stick_y",
        "right_stick_vec",
        "right_stick_x",
        "right_stick_y",
        "left_trigger",
        "right_trigger",
        "dpad_vec",
    ]
    assert {"a", "b", "x", "y", "dpad_up", "left_shoulder", "left_stick_press", "touchpad"} <= set(names)
    assert CHOICES["a"] == "A (bottom)"


def test_selected_keeps_the_order_and_drops_unknown() -> None:
    text = "a, left_stick_vec, nope, a,  right_trigger"
    assert [o.name for o in selected(text)] == ["a", "left_stick_vec", "right_trigger"]
    assert unknown(text) == ["nope"]
    assert selected("") == []


def test_which_messages_change_an_output() -> None:
    assert changes(BY_NAME["left_stick_vec"], gm.axis(1, 5, 0.0))
    assert changes(BY_NAME["left_stick_x"], gm.axis(1, 5, 0.0)), "x is read with y: it may move with it"
    assert not changes(BY_NAME["left_stick_vec"], gm.axis(2, 5, 0.0))
    assert changes(BY_NAME["right_trigger"], gm.axis(5, 5, 0.0))
    assert changes(BY_NAME["a"], gm.button(0, True, 0.0))
    assert not changes(BY_NAME["a"], gm.button(1, True, 0.0))
    assert changes(BY_NAME["dpad_vec"], gm.hat(0, 1, 0.0))
    assert not changes(BY_NAME["dpad_vec"], gm.button(11, True, 0.0)), "the hat message follows"
    assert changes(BY_NAME["dpad_up"], gm.button(11, True, 0.0))


def test_buttons_are_events() -> None:
    assert is_event(BY_NAME["a"])
    assert not is_event(BY_NAME["left_stick_vec"])
    assert not is_event(BY_NAME["dpad_vec"])


def test_values_from_one_state() -> None:
    assert list(value(BY_NAME["left_stick_vec"], AXES, BUTTONS, RAW)) == pytest.approx([0.6, 0.8])
    assert value(BY_NAME["left_stick_x"], AXES, BUTTONS, RAW) == pytest.approx(0.6)
    assert value(BY_NAME["left_stick_y"], AXES, BUTTONS, RAW) == pytest.approx(0.8)
    assert value(BY_NAME["left_trigger"], AXES, BUTTONS, RAW) == 0.25
    assert value(BY_NAME["a"], AXES, BUTTONS, RAW) is True
    assert value(BY_NAME["b"], AXES, BUTTONS, RAW) is False
    assert list(value(BY_NAME["dpad_vec"], AXES, BUTTONS, RAW)) == [1, -1], "SDL: up is negative"


def test_y_up_flips_sticks_and_dpad() -> None:
    up = Shaping(dead_zone=0.0, y_up=True)
    assert list(value(BY_NAME["left_stick_vec"], AXES, BUTTONS, up)) == pytest.approx([0.6, -0.8])
    assert value(BY_NAME["left_stick_y"], AXES, BUTTONS, up) == pytest.approx(-0.8)
    assert list(value(BY_NAME["dpad_vec"], AXES, BUTTONS, up)) == [1, 1]
    assert value(BY_NAME["left_trigger"], AXES, BUTTONS, up) == 0.25, "triggers are not flipped"


def test_radial_dead_zone() -> None:
    zone = Shaping(dead_zone=0.2, y_up=False)
    assert stick(-0.18, 0.05, zone) == (0.0, 0.0), "a resting stick reads 0"
    x, y = stick(0.6, 0.8, zone)  # length 1: still reaches 1
    assert math.hypot(x, y) == pytest.approx(1.0)
    assert (x, y) == pytest.approx((0.6, 0.8))
    x, y = stick(0.6, 0.0, zone)  # halfway between the zone and the edge
    assert (x, y) == pytest.approx((0.5, 0.0))
    assert stick(1.0, 1.0, zone) == pytest.approx((math.sqrt(0.5), math.sqrt(0.5))), "never beyond 1"
