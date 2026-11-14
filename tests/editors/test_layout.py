"""Shared editor layout: nothing that breaks Quasar's rendering for the whole page."""

import pytest
from nicegui import ui
from nicegui.testing import User

import haybale_protokol.editor_layout as layout

pytestmark = pytest.mark.anyio

#: QScrollArea props Quasar types as Object: a string there is spread character by character
#: into a style and throws in the browser, which stops every editor on the page.
OBJECT_PROPS = ("thumb-style", "bar-style", "vertical-thumb-style", "horizontal-thumb-style")


async def test_scroll_area_passes_no_string_object_props(user: User) -> None:
    holder: dict[str, ui.scroll_area] = {}

    @ui.page("/")
    def page() -> None:
        holder["area"] = layout.scroll_area()

    await user.open("/")
    props = holder["area"].props
    for name in OBJECT_PROPS:
        assert not isinstance(props.get(name), str), f"{name} must not be a string"
