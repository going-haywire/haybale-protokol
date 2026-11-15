# haybale-protokol-midi — component index (v0.0.5)

## node
- `haybale-protokol-midi:node:MidiReceiveNode` — MIDI Receive — Triggered for each MIDI message on its gates that passes its kind, channel and number  _tags: midi, receive, note, cc, controller, protokol_
- `haybale-protokol-midi:node:MidiSendNode` — MIDI Send — Sends one MIDI message to its gates each time it runs  _tags: midi, send, note, cc, controller, protokol_

## state
- `haybale-protokol-midi:state:MidiState` — Protokol MIDI — Registers the MIDI driver with Protokol
