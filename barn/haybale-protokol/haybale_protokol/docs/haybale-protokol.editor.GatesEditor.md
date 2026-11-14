# Gates

`haybale-protokol:editor:GatesEditor` · kind: editor

The project's gates and their Lines

## Details

- **default_slot**: `action`
- **opens**: `OpenBehavior.REQUIRED`
- **order**: `100`

## Notes

One row per gate: its name, protocol and direction, and below them its status.

The status says whether its Line is open (and by how many users), closed, or why the gate
cannot be used: protocol not installed, unbound device, or a malformed entry. With EDIT a
row can be edited or deleted and the header adds a gate. An unbound gate offers "Bind…",
which selects its device for the Device editor.
