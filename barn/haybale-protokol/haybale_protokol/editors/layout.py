"""Layout pieces the three Protokol editors share, following the haywire design guide."""

from __future__ import annotations

from nicegui import ui

#: Content as wide as the area, so rows truncate instead of overflowing. The scrollbar keeps
#: Quasar's default, as everywhere else in the studio: ``thumb-style``/``bar-style`` are Object
#: props in Quasar, and the string form shown in design guide §9.4 throws in the browser and
#: stops every editor on the page.
_CONTENT_WIDTH = 'content-style="width: 100%" content-active-style="width: 100%"'

#: Classes of a selectable list row (design guide §8.4); add ``ACTIVE_ROW`` when it is selected.
LIST_ROW = "w-full px-2 py-1.5 items-center gap-2 no-wrap rounded cursor-pointer hw-list-item-hover"
ACTIVE_ROW = "hw-list-item-active"


def scroll_area() -> ui.scroll_area:
    """A full-width scroll area whose content is as wide as the area."""
    return ui.scroll_area().classes("flex-1 w-full").props(_CONTENT_WIDTH)


def list_row(*, active: bool = False) -> ui.row:
    """A selectable row: hover from the theme, ``--hw-bg-active`` when ``active``."""
    return ui.row().classes(f"{LIST_ROW} {ACTIVE_ROW}" if active else LIST_ROW)
