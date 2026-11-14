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


#: A list entry of several lines: hover and active like ``list_row``, children stacked.
LIST_BLOCK = "w-full px-2 py-1.5 gap-0 rounded hw-list-item-hover"

#: A splitter's divider: a faint line in the theme's separator colour (falls back to the border).
SPLITTER_SEPARATOR = 'separator-style="background-color: var(--hw-separator, var(--hw-border))"'


def list_block(*, active: bool = False) -> ui.column:
    """A list entry whose first row holds its controls and whose next rows hold its details."""
    return ui.column().classes(f"{LIST_BLOCK} {ACTIVE_ROW}" if active else LIST_BLOCK)
