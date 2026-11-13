# Protokol

`haybale-protokol:state:ProtokolState` · kind: state

Protocol drivers, the project's gates and the Lines they share

## Notes

Owns the Protocol drivers and the open Lines; reads the Gate file and the Device list.

One per app, shared by every session and by execution. Lines run on their own threads, so
every change is published as a payload-free ``ProtokolChanged`` scheduled onto the loop.
