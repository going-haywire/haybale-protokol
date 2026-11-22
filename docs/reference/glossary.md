# Ubiquitous Language — haybale-protokol

## Gates

| Term | Definition | Aliases to avoid |
|------|-----------|-----------------|
| **Gate** | A named, saved connection point to one control protocol (an OSC port, a MIDI device port, a gamepad, an Art-Net universe) that graphs refer to by name only. | endpoint (taken by SignalPeer and Farmhand), port (clashes with node ports), route, patch point |
| **Input gate** | A **Gate** that brings messages from the outside into Haywire. | receiver, source |
| **Output gate** | A **Gate** that carries messages from Haywire to the outside. | sender, sink |
| **Two-way gate** | A **Gate** that is both input and output over one shared channel; only where the protocol has one (an OSC TCP connection, a gamepad). | duplex gate, bidirectional endpoint |

## Devices and storage

| Term | Definition | Aliases to avoid |
|------|-----------|-----------------|
| **Device** | A piece of hardware this machine knows (a MIDI port, a gamepad), under a name the user chose, mapped to whatever the OS calls it. | hardware id, port name (that is the OS's name, not ours) |
| **Device list** | The per-machine list of **Devices**, shared by every project on the machine. Holds nothing about network peers. | machine config, device settings |
| **Gate file** | The project's list of **Gates**, committed with the project. | endpoint setup, OSC config |
| **Unbound gate** | A **Gate** whose **Device** name is not in this machine's **Device list**; its nodes show this as their status. | missing device, broken gate |
| **Not plugged in** | A **Gate** whose **Device** is in the **Device list**, but whose port is not on this machine now (unplugged, switched off). Receive nodes wait for it and reconnect. | disconnected, offline, absent |
| **Gate health** | Whether a **Gate** works now, and why not: working, closed, unbound, not plugged in, or error. The one source every view reads. | gate status (the status texts are its reasons), state |

## Protocols

| Term | Definition | Aliases to avoid |
|------|-----------|-----------------|
| **Protocol haybale** | A haybale of this family that adds one control protocol (`haybale-protokol-osc`, `-midi`, `-gamepad`, `-artnet`) on top of the base `haybale-protokol`. | plugin, extension |
| **Line** | The one open port or device connection that **Gates** and the monitor share: one **Line** per protocol and port, or per **Device**, in either direction. | listener (an Observable store callback), socket, connection, port |
| **Line cache** | The last message a **Line** saw per address, channel or axis; what a Receive node starts with when its **Start value** flag is on. | latest value store, value buffer |
| **Start value** | A Receive node flag: fire once with the **Line cache** when its run starts. On by default for states (faders, axes, Art-Net, OSC), off for events (notes, buttons). | replay, initial trigger |
| **Protocol driver** | What a **Protocol haybale** hands the base while it is enabled: how to open its connections, read and send its messages, and describe them in the monitor. | adapter (an Adapter is a Haywire type converter), backend |

## OSC messages

| Term | Definition | Aliases to avoid |
|------|-----------|-----------------|
| **Arg shape** | The space-separated list of argument tokens an OSC node expects or sends (`vf3 vf3 i s`): OSC type tags plus Haywire groupings (`vi2`–`vi4`, `vf2`–`vf4`, `m3`, `m4`) that map to vector and matrix types, and, on Receive only, `_` / `_n` to skip one or n arguments (a Send node has no skip: an unconnected inlet sends its own value). The node's single source of truth for its argument pins: typing it rebuilds the pins, and growing, removing or reordering a pin rewrites it. | carrier structure (CARRIER is a Haywire type), signature, type tag string (that is OSC's own wire form) |
| **OSC bundle** | A group of OSC messages sharing one timetag; split into its messages on receive. | bundle (Haywire's BUNDLE is a different thing) |
| **Blob** | An OSC argument of raw bytes, delivered as `BYTES` and decoded by separate nodes. | binary, payload |

## Editors

| Term | Definition | Aliases to avoid |
|------|-----------|-----------------|
| **Gates editor** | The ACTION-slot editor: the project's **Gates** with their **Gate health** above, the **Device pane** below. | endpoint editor, OSC editor |
| **Monitor** | The EDIT-slot tab that shows, filters and logs live traffic on **Lines**, including **Lines** no **Gate** uses yet. | sniffer, traffic log, console |
| **Device pane** | The lower pane of the **Gates editor**: the **Gate**, **Device** or **Line** in the **Protokol selection**, or the **Device list**. Replaced the Device editor (design §10.4). | Device editor (removed), device panel, inspector |
| **Protokol selection** | The **Gate**, **Line** or **Device** currently selected in one session; what the **Device pane** follows. | current gate, focus |

## Relationships

- A graph stores only a **Gate**'s name; everything else about the **Gate** lives outside the graph.
- A **Gate** has one direction, except a **Two-way gate**. UDP (OSC, Art-Net) and MIDI gates are always one-way: their in and out are unrelated ports or separate device ports.
- A MIDI or gamepad **Gate** names one **Device**; network **Gates** (OSC, Art-Net) name none.
- The colleague test decides where a value lives: if it stays correct when a colleague opens the project on their own machine with the same kind of hardware, it belongs in the **Gate file**; otherwise in the **Device list**.
- Each **Protocol haybale** has one **Protocol driver**, registered while the haybale is enabled. A **Gate** whose protocol has no driver shows "protocol not installed" as its status.
- A **Gate** uses one **Line**; a **Line** serves any number of **Gates** and monitors. Only a **Line** opens a port or device, so nothing fights over one.
- The monitor can open a **Line** no **Gate** uses yet; such a **Line** can be promoted to a named **Gate**.
- Receive nodes read from an **Input gate**; Send nodes write to an **Output gate**. "Receive"/"Send" are node verbs, "input"/"output" are gate directions.

## Example dialogue

> **Dev:** "The OSC Event node in this graph says `touchosc-in` is missing — is that a crash?"
> **Domain expert:** "No. The graph only stores the **Gate** name. This project has no **Input gate** called `touchosc-in` yet, so the node shows it as its status."
> **Dev:** "Can two Receive nodes use the same **Input gate**?"
> **Domain expert:** "Yes. That's the point of a **Gate**: one place opens the port, and any number of nodes read from it."

## Flagged ambiguities

- "endpoint" (from the original OSC handoff) was used for what is now a **Gate**. Resolved: **Gate**, because "endpoint" already names a SignalPeer and the Farmhand MCP endpoint in Haywire's glossary, and fits a gamepad poorly.
- "main slot" was used for the centre slot. Resolved: it is the **EDIT** slot; left/main/right/bottom are Haywire's removed slot names.
- "carrier structure" was used for an OSC node's argument layout. Resolved: **Arg shape**; `CARRIER` is Haywire's type for values with stamped fields.
- "bundle" means two things. Resolved: always say **OSC bundle** for the transport group; `BUNDLE` stays Haywire's carrier type.
- "surfaces" was used for the three slots side by side. Resolved: say "slots"; a Haywire **Surface** is a place panels appear (ADR-0029).
