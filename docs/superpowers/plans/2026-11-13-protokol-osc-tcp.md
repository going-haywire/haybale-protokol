# OSC over TCP — Implementation Plan (Plan 2 of 6)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** OSC gates over TCP, as a client or a server, with both framings, reconnect with backoff, and Two-way gates, so a graph can talk to a TCP peer (for example TouchOSC over TCP, a show controller) through the existing OSC Receive and Send nodes.

**Architecture:** `OscDriver` gains a `tcp` transport. A TCP Line is one `TcpClientConnection` (one socket, a connect-and-read daemon thread that reconnects with backoff) or one `TcpServerConnection` (a listening socket, an accept thread, one reader thread per peer). Both cut the byte stream into OSC packets with a `FrameReader` for OSC 1.0 (32-bit length prefix) or OSC 1.1 (SLIP), and reuse Plan 1's packet split (`_split`) and `build_message`. Nodes don't change: a Two-way gate already serves `use(..., "in")` and `use(..., "out")` (Plan 1, `ProtokolState.use`).

**Tech Stack:** Python 3.12 `socket`/`threading`, `python-osc` 1.10.2 (`pythonosc.slip`), pytest.

**Spec:** [docs/design.md](../../design.md) §3.1, §3.3, §3.4; terms from [docs/reference/glossary.md](../../reference/glossary.md). Builds on Plan 1 (branch `plan-1-base-osc-udp`).

## Global Constraints

- Everything in Plan 1's Global Constraints still holds: no haywire-repo changes or links, `uv run --frozen`, glossary terms, no ADRs, status texts instead of errors.
- Framings: OSC 1.0 = 4-byte big-endian length prefix; OSC 1.1 = SLIP (`pythonosc.slip`). A per-gate setting; default `1.1`.
- A client reconnects with backoff 0.5 s, 1 s, 2 s, 4 s, then 5 s, while its Line has users. Its status shows `reconnecting (n)`.
- Sends while disconnected are **dropped and counted, never queued**.
- A server gate accepts many peers; a send goes to all of them.
- TCP gates may be `in`, `out` or `two-way`; UDP stays one-way.
- The grace period keeps a TCP peer across a graph restart (same socket).
- Work happens on branch `plan-2-osc-tcp`, cut from `plan-1-base-osc-udp`. One commit per task; no push, no merge.

## Gate file format (new keys)

```toml
[gates.desk]                # client: we connect to the peer
protocol = "osc"
direction = "two-way"
transport = "tcp"
role = "client"             # default "client"
host = "10.0.0.5"
port = 3032
framing = "1.1"             # "1.0" (length prefix) or "1.1" (SLIP, default)

[gates.tablets]             # server: peers connect to us
protocol = "osc"
direction = "two-way"
transport = "tcp"
role = "server"
port = 9000
bind = "0.0.0.0"            # default all interfaces
```

Line keys: `tcp-client <host>:<port>` and `tcp-server <bind>:<port>`. Gates with equal keys share one Line whatever their direction. Two gates on one key with different framings get the status `gate 'x': framing differs from gate 'y' on the same line`.

## Review Focus

1. **The peer goes away mid-stream (server restart, cable pulled).** Expect the client's status to change to `reconnecting (1)`, sends to be dropped and counted, and the connection to come back on its own without a graph restart. → Task 3 `test_reconnects_after_peer_restart`.
2. **A frame split across reads, or several frames in one read.** Expect exactly the sent messages, in order. → Task 1 `test_reader_reassembles_split_and_joined_frames`.
3. **A peer sending garbage or an absurd length prefix.** Expect that peer's connection dropped (server) or reconnected (client), counted as bad, and no unbounded buffer. → Task 1 `test_oversized_length_is_rejected`, Task 4 `test_garbage_peer_is_dropped`.
4. **A graph restart within the grace period.** Expect the same TCP socket, so the peer sees no disconnect. → Task 5 `test_restart_within_grace_keeps_peer`.
5. **Shutdown while connecting or blocked in accept/recv.** Expect `close()` to return within about 1 s, with no thread left alive. → Task 3 `test_close_while_connecting`, Task 4 `test_close_stops_all_threads`.

---

### Task 1: Framing

**Files:** Create `barn/haybale-protokol-osc/haybale_protokol_osc/framing.py`; Test `tests/osc/test_framing.py`

**Interfaces:**
- Produces: `Framing = Literal["1.0", "1.1"]`; `encode_frame(packet: bytes, framing: Framing) -> bytes`; `class FrameReader: __init__(framing: Framing, max_frame: int = MAX_FRAME)`, `feed(data: bytes) -> list[bytes]` (complete packets in order); `class FrameError(ValueError)` for a length over `max_frame` or a SLIP buffer over `max_frame` with no END. `MAX_FRAME = 1 << 20`.

- [ ] Tests: `test_length_prefix_round_trip`, `test_slip_round_trip_with_escaped_bytes` (packet containing `0xC0` and `0xDB`), `test_reader_reassembles_split_and_joined_frames` (both framings: feed byte by byte, then three frames in one feed), `test_oversized_length_is_rejected`, `test_slip_without_end_over_limit_is_rejected`, `test_empty_slip_frames_are_skipped` (`END END`). Watch FAIL → implement → PASS → commit.

### Task 2: Gate options and Line keys for TCP

**Files:** Modify `barn/haybale-protokol-osc/haybale_protokol_osc/driver.py` (`OscDriver.line_key`, `open`); Test `tests/osc/test_tcp_driver.py`

**Interfaces:**
- `OscDriver.line_key`: `transport = "tcp"` → `LineKey("osc", "tcp-client host:port")` / `"tcp-server bind:port"`. Validation `ValueError`s: unknown `role`; unknown `framing`; client without `host`; non-string `host` or `bind` (also for UDP, folding in Plan 1 minor #15); `two-way` with UDP (unchanged).
- Framing conflict: `OscDriver.line_key` cannot see other gates, so `ProtokolState.use` gets a check. Add a `ProtocolDriver.line_options(gate) -> Mapping[str, Any]` (default: empty) that names options which must agree on a shared Line. `use` compares them with the Line's first gate and returns `gate 'x': framing differs from gate 'y' on the same line`. The base adds `Line.gate: Gate | None` (the first gate). `FakeDriver` in the tests gets `line_options` returning `{}`.
- [ ] Tests: `test_tcp_line_keys`, `test_tcp_bad_options_raise` (parametrized), `test_two_way_tcp_is_allowed`, `test_framing_conflict_is_status` (base test with a FakeDriver whose `line_options` returns `{"framing": …}`). FAIL → implement → PASS → commit.

### Task 3: TCP client connection

**Files:** Modify `driver.py` (`TcpClientConnection`); Test `tests/osc/test_tcp_client.py` (a small threaded TCP server helper in `tests/osc/conftest.py` that records frames and can send frames to its peer, for both framings).

**Interfaces:**
- `TcpClientConnection(host: str, port: int, framing: Framing)`, implementing `Connection`:
  - `start(deliver)` never raises for an unreachable peer. It starts thread `protokol-osc-tcp-client-<port>`, which connects, reads, and on any error waits for the next backoff step (`BACKOFF_S = (0.5, 1.0, 2.0, 4.0, 5.0)`, then 5 s for good) and reconnects. A successful connection resets the backoff.
  - `status`: `connected to tcp host:port · sent n · dropped m`, or `reconnecting (n) · ...`, with `· b bad` when bad frames were seen.
  - `send(message)`: when not connected, count it as dropped and return False. Otherwise `sendall(encode_frame(build_message(...), framing))` under a send lock; an `OSError` drops the socket, counts the message as dropped, and lets the thread reconnect.
  - `close()`: sets the closing event, shuts the socket down and joins. Connecting uses a timeout (≤ 0.5 s) and backoff waits use `Event.wait`, so `close()` returns within about 1 s.
  - Received packets go through Plan 1's `_split`, each message delivered with `extra["timetag"]` where it came from an OSC bundle. A `FrameError` or unparsable packet counts as bad; a `FrameError` also drops the connection, because the stream is out of sync.
- [ ] Tests (each for both framings where it matters): `test_client_receives_from_server`, `test_client_sends_to_server`, `test_sends_while_disconnected_are_dropped_and_counted`, `test_reconnecting_status_counts_attempts`, `test_reconnects_after_peer_restart`, `test_close_while_connecting` (unroutable peer, e.g. port 1 on 127.0.0.1 refused, plus a 10.255.255.1 timeout case; `close()` < 1.5 s, thread dead), `test_bad_frame_reconnects`. FAIL → implement → PASS → commit.

### Task 4: TCP server connection

**Files:** Modify `driver.py` (`TcpServerConnection`); Test `tests/osc/test_tcp_server.py`

**Interfaces:**
- `TcpServerConnection(bind: str, port: int, framing: Framing)`:
  - `start(deliver)` binds and listens (backlog 8). A bind error raises `OSError`, so the Line status is `cannot open: ...` as in Plan 1. Then it starts `protokol-osc-tcp-server-<port>` (accept loop, 0.2 s timeout), and one `protokol-osc-tcp-peer-<port>-<n>` reader per peer.
  - `send(message)`: encodes once and `sendall`s to every peer. A peer that fails is closed and removed. Returns True when at least one peer got it; with no peers it counts a drop and returns False.
  - `status`: `serving on tcp bind:port · p peers · sent n · dropped m`.
  - A peer whose stream is bad (`FrameError`) is closed, counted, and the others carry on.
  - `close()` closes the listener and every peer and joins all threads.
- [ ] Tests: `test_server_receives_from_two_peers`, `test_send_goes_to_all_peers`, `test_send_without_peers_is_dropped`, `test_peer_disconnect_is_removed`, `test_garbage_peer_is_dropped`, `test_port_in_use_is_status`, `test_close_stops_all_threads`. FAIL → implement → PASS → commit.

### Task 5: Nodes over TCP, end to end

**Files:** Test `tests/osc/test_tcp_end_to_end.py`; Modify `barn/haybale-protokol/haybale_protokol/NOTES.md` (TCP gate examples; correct "gates on the same port share one Line" to "gates with the same Line key", Plan 1 minor #10), `barn/haybale-protokol-osc/haybale_protokol_osc/NOTES.md`, regenerated docs.

- [ ] Tests: `test_receive_and_send_over_two_way_client_gate` (a test TCP server sends `/in 1.5`; the graph's Receive → Send on the same Two-way gate replies `/out 1.5`; the server sees it), `test_server_gate_forwards_to_peers` (two test clients; a message from one comes back to both), `test_restart_within_grace_keeps_peer` (grace 5 s; stop and start the graph; the test server saw exactly one accept), `test_missing_peer_does_not_block_start` (client gate to a closed port; the graph starts, and the Send status shows dropped messages and `reconnecting`).
- [ ] `uv run --frozen pytest -q`, `ruff check .`, `mypy barn/...` all clean; `haywire docs` for both haybales. Report to the owner. No `haywire share`.

## Deferred

- OSCQuery (Plan 6), Monitor taps on TCP Lines (Plan 3), TLS (out of scope: not in the design).
- Plan 1 minors not touched here (#6–#9, #11–#14, #16, #17) go to the cleanup slice.
