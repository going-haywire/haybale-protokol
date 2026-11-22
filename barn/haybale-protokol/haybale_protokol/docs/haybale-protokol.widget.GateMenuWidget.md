# GateMenuWidget

`haybale-protokol:widget:GateMenuWidget` · kind: widget

Pick gates as chips from the gates that fit the node, each coloured by its state

## Details


## Notes

A select of gates; its behaviour is set by plain properties, as the port saves them.

Each chosen gate shows as a chip coloured by its state: success when usable, warning when this
machine cannot use it now (protocol not installed, device unbound), danger when there is no such
gate or it is of another protocol or direction. The select takes input only in edit mode.

Properties (``GateMenuWidget.config(properties={...})``):

- ``protocol``: the gates to offer and check, e.g. ``"osc"``.
- ``direction``: ``"in"`` or ``"out"``; two-way gates fit both.
- ``multiple`` (default ``True``): several gates, stored as ``"a, b"``; ``False`` for exactly one.
- ``typed`` (default ``True``): a name typed and confirmed with Enter is kept even when no such
  gate exists yet.

The offered gates are read from the project each time the widget is drawn, so new gates appear.
