# Protokol OSC

OSC over UDP for Haywire, on top of `haybale-protokol`: an OSC Receive node and an OSC Send
node, each using a gate from the project's `.haywire/protokol.toml` (see the Protokol notes
for the file format).

## OSC Receive

Runs its flow for each message on its input gate whose address matches **Address**, an OSC
address pattern (`*`, `?`, `[0-9]`, `{a,b}`; empty takes everything). Each wildcard gets a
`match_N` outlet, which takes the type of whatever you connect it to.

**Arg Shape** lists the arguments: OSC type tags (`i f d h s b T r`), groupings
`vi2`–`vi4`, `vf2`–`vf4`, `m3`, `m4` for vectors and matrices, and `_` / `_n` to skip
arguments. Empty gives one `args` list. A message that does not fit is skipped and counted
in `status`. By default the node fires once at start with the last message the gate saw
(**Start Value**) and keeps only the newest message when its flow runs behind.

## OSC Send

Sends **Address** with one argument per inlet, in inlet order. Connect anything to the empty
inlet to add an argument. Vectors go out as their components (`vf3` → three `f`). Use `d` or
`h` in the shape for 64-bit numbers. An int that does not fit a 32-bit `i` is dropped, and
`status` says which argument it was.

The Arg shape and the pins follow each other: typing the shape rebuilds the pins, and
growing, unplugging (a grown pin) or reordering pins rewrites the shape.
