"""Gamepad messages: scaling, the d-pad as a hat, rumble checks, test messages, descriptions."""

import pytest

import haybale_protokol_gamepad.gamepad_messages as gm


def test_sticks_scale_to_minus_one_one() -> None:
    assert gm.axis(0, 32767, 0.0).args == (1.0,)
    assert gm.axis(0, -32768, 0.0).args == (-1.0,), "SDL's extra negative step is clamped"
    assert gm.axis(1, 0, 0.0).args == (0.0,)
    message = gm.axis(2, -16384, 0.0)
    assert message.address == "axis 2"
    assert message.extra == {"kind": "axis", "index": 2}
    assert message.args[0] == pytest.approx(-0.5, abs=1e-4)


def test_triggers_scale_to_zero_one() -> None:
    assert gm.axis(4, 32767, 0.0).args == (1.0,)
    assert gm.axis(5, 0, 0.0).args == (0.0,)
    assert gm.axis(5, -5, 0.0).args == (0.0,), "a trigger never goes below rest"


def test_buttons() -> None:
    message = gm.button(0, True, 0.0)
    assert (message.address, message.args, message.extra["kind"]) == ("button 0", (True,), "button")


@pytest.mark.parametrize(
    ("held", "hat"),
    [
        (set(), (0, 0)),
        ({11}, (0, -1)),
        ({12}, (0, 1)),
        ({13}, (-1, 0)),
        ({14, 11}, (1, -1)),
        ({13, 14}, (0, 0)),
    ],
)
def test_dpad_as_hat(held: set[int], hat: tuple[int, int]) -> None:
    assert gm.dpad_hat(held) == hat
    assert list(gm.hat(*hat, 0.0).args[0]) == list(hat)


def test_rumble_checks_its_values() -> None:
    assert gm.rumble(0.5, 1, 200, 0.0).args == (0.5, 1.0, 200)
    assert gm.rumble(0, 0, 0.0, 0.0).args == (0.0, 0.0, 0)
    for low, high, ms in [(1.5, 0, 10), (-0.1, 0, 10), ("a", 0, 10), (True, 0, 10), (0, 0, -1), (0, 0, 2.5)]:
        with pytest.raises(ValueError, match="must be"):
            gm.rumble(low, high, ms)
    with pytest.raises(ValueError, match="duration"):
        gm.rumble(0, 0, gm.RUMBLE_MAX_MS + 1)


def test_parse_test_message() -> None:
    assert gm.parse_test_message("rumble 0.5 1 300").args == (0.5, 1.0, 300)
    assert gm.parse_test_message("rumble 0.2 0.3").args == (0.2, 0.3, 200)
    assert gm.parse_test_message("stop").args == (0.0, 0.0, 0)
    for text in ["", "rumble", "rumble 2 0", "rumble a b", "axis 0 1"]:
        with pytest.raises(ValueError, match="gamepad test message"):
            gm.parse_test_message(text)


def test_describe() -> None:
    assert gm.describe(gm.axis(0, 16384, 0.0)) == "axis 0 leftx = 0.500"
    assert gm.describe(gm.button(1, True, 0.0)) == "button 1 b down"
    assert gm.describe(gm.button(11, False, 0.0)) == "button 11 dpup up"
    assert gm.describe(gm.hat(1, -1, 0.0)) == "hat 0 dpad (1, -1)"
    assert gm.describe(gm.rumble(0.5, 0.25, 100, 0.0)) == "rumble low 0.50 high 0.25 for 100 ms"
    assert gm.describe(gm.rumble(0, 0, 0, 0.0)) == "rumble stop"
