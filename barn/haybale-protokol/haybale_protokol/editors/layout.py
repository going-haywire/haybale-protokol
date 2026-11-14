"""Layout pieces the three Protokol editors share, following the haywire design guide."""

from __future__ import annotations

from nicegui import ui

#: Design guide §9.4: 4px scrollbars, the thumb in ``--hw-border-strong``, a transparent track.
_SCROLLBAR = (
    'thumb-style="background: var(--hw-border-strong); border-radius: 4px; width: 4px;"'
    ' bar-style="background: transparent; width: 4px;"'
    ' content-style="width: 100%" content-active-style="width: 100%"'
)

#: Classes of a selectable list row (design guide §8.4); add ``ACTIVE_ROW`` when it is selected.
LIST_ROW = "w-full px-2 py-1.5 items-center gap-2 no-wrap rounded cursor-pointer hw-list-item-hover"
ACTIVE_ROW = "hw-list-item-active"


def scroll_area() -> ui.scroll_area:
    """A full-width scroll area with the design guide's scrollbar."""
    return ui.scroll_area().classes("flex-1 w-full").props(_SCROLLBAR)


def list_row(*, active: bool = False) -> ui.row:
    """A selectable row: hover from the theme, ``--hw-bg-active`` when ``active``."""
    return ui.row().classes(f"{LIST_ROW} {ACTIVE_ROW}" if active else LIST_ROW)
