# GateSelectWidget

`haybale-protokol:widget:GateSelectWidget` · kind: widget

Pick gates as chips from the gates that fit the node; typed names are kept

## Details


## Notes

A multiple select with chips, like the Models editor's library filter.

Config (``GateSelectWidget.config(properties={...})``), plain values since a port saves it:

- ``protocol``: which gates to offer, e.g. ``"osc"``.
- ``direction``: ``"in"`` or ``"out"``; two-way gates are offered for both.

The offered gates are read from the project each time the widget is drawn, so new gates appear.

A name typed and confirmed with Enter is kept even when no such gate exists yet; the node's
status then reports it.
