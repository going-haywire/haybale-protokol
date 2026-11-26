# haybale-protokol-midi — component index (v0.0.10)

## node
- `haybale-protokol-midi:node:MidiEventNode` — MIDI Event — Triggered for each MIDI message on its gates that passes its kind, channel and number  _tags: midi, receive, note, cc, controller, protokol_
- `haybale-protokol-midi:node:SendMidiNode` — Send MIDI — Sends one MIDI message to its gates each time it runs  _tags: midi, send, note, cc, controller, protokol_

## state
- `haybale-protokol-midi:state:MidiState` — Protokol MIDI — Registers the MIDI driver with Protokol
