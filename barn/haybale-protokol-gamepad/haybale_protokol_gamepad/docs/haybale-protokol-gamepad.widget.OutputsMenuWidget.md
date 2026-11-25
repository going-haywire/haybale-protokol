# OutputsMenuWidget

`haybale-protokol-gamepad:widget:OutputsMenuWidget` · kind: widget

Pick a gamepad node's outputs as chips; each becomes an outlet, in the order picked

## Details

- **min_width**: `160`

## Notes

A multiple select of the outputs in ``gamepad_outputs.OUTPUTS``, saved as ``"a, b"``.

The menu lists each output by its label (``Left stick (x, y)``); a chosen one shows as a chip
with its outlet name (``left_stick_vec``), and hovering the chip shows the label and the
outlet's type. The select takes input only in edit mode.
