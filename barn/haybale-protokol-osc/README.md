# Protokol OSC

# Protokol OSC

OSC over UDP and TCP for Haywire, on top of `haybale-protokol`: an OSC Receive node and an OSC Send
node, each using a gate from the project's `.haywire/protokol.toml` (see the Protokol notes
for the file format).

## TCP

A TCP gate is a client (`role = "client"`, connects to `host`) or a server
(`role = "server"`, accepts any number of peers on `bind`). Choose the framing your peer
speaks: `framing = "1.0"` (length prefix) or `"1.1"` (SLIP, the default). A client keeps
reconnecting (0.5 s, 1 s, 2 s, 4 s, then every 5 s) and shows `reconnecting (n)`; anything sent
while it is disconnected is dropped and counted, never queued. A server sends each message to
all its peers. TCP gates may be `two-way`, so one gate can feed an OSC Receive and an OSC Send.

A peer that disappears without closing (power cut, lost Wi-Fi) is noticed by TCP keepalive
after about 11 s; a client then reconnects. A peer that stops reading is disconnected once
it holds up a send for 0.2 s, rather than slowing the graph down.

## Gates on a node

A node's **Gate** setting takes one or more gates. Pick them as chips from the list, which
offers this project's OSC gates that fit the node (input or two-way for Receive, output or
two-way for Send), or type a name and press Enter. OSC Receive listens on every listed gate;
its **From gate** outlet says where a message came in. OSC Send sends each message to every
listed gate. A listed gate that cannot be used is reported in `status`; the others still work.

## OSC Receive

Runs its flow for each message on its input gate whose address matches **Address**, an OSC
address pattern (`*`, `?`, `[0-9]`, `{a,b}`; empty takes everything). Each wildcard gets a
`match_N` outlet, which takes the type of whatever you connect it to.

**Arg Shape** lists the arguments: OSC type tags (`i f d h s b T r`), groupings
`vi2`–`vi4`, `vf2`–`vf4`, `m3`, `m4` for vectors and matrices, and `_` / `_n` to skip
arguments. The `args` outlet always carries every argument as a list; each token adds its own outlet. A message that does not fit is skipped and counted
in `status`. By default the node fires once at start with the last message the gate saw
(**Start Value**) and keeps only the newest message when its flow runs behind.

## OSC Send

Sends **Address** with one argument per inlet, in inlet order. Connect anything to the empty
inlet to add an argument. Vectors go out as their components (`vf3` → three `f`). Use `d` or
`h` in the shape for 64-bit numbers. An int that does not fit a 32-bit `i` is dropped, and
`status` says which argument it was. Each control tick sends, unless the **Only send changes** setting is on: then
a tick sends only when the address, type tags or values differ from the last message sent.

The Arg shape and the pins follow each other: typing the shape rebuilds the pins, and
growing, unplugging (a grown pin), removing a pin from its menu or reordering pins rewrites
the shape. Each of these is one undo step. A pin's label is its token (`f`, `vf3`).

<!-- marketstall:share-url:start -->
Always the latest (tracks the current branch):

```sh
https://github.com/going-haywire/haybale-protokol/blob/master/marketstall.toml
```

Frozen to this version:

```sh
https://github.com/going-haywire/haybale-protokol/blob/v0.0.4/marketstall.toml
```
<!-- marketstall:share-url:end -->

OSC for haybale-protokol: UDP and TCP gates, OSC Receive and Send nodes

## Nodes
### Protokol
- **OSC Receive** — Triggered for each OSC message on an input gate that matches the address pattern
- **OSC Send** — Sends one OSC message to an output gate each time it runs

## States
- **Protokol OSC** — Registers the OSC driver with Protokol
