# Device

`haybale-protokol:editor:DeviceEditor` · kind: editor

The device or Line in the Protokol selection

## Details

- **default_slot**: `context`
- **opens**: `OpenBehavior.REQUIRED`
- **order**: `100`

## Notes

Follows the Protokol selection.

- A device: its OS name, and whether the protocol sees it connected. With ADMIN: edit or
  delete it, or map a gate's device name that this machine does not know yet.
- A gate: its options, its Line's status and users, and the Line cache.
- A Line: its key, status, users and cache.
- Nothing: the Device list.
