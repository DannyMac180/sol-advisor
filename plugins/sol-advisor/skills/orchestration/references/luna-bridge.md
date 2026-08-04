# Luna primary-to-task bridge

This canonical protocol makes the primary Sol task's relationship with each
user-visible Luna task auditable. Use it with the complete
[Luna task-lane contract](luna-task-lane.md); it does not replace that contract.

## Identity and lifecycle

Create one immutable **BRIDGE CORRELATION ID** before `create_thread`. Record the
project's `projectId`, then append the real `threadId` and `hostId` when available.
If creation initially returns `clientThreadId`, record it only as historical setup
evidence: it is a handle, never a thread-tool argument.

Record **BRIDGE STATE** as exactly one of `pending`, `ready`, `running`,
`needs_attention`, `completed`, or `blocked`.

The normal lifecycle is `pending -> ready -> running -> completed`. A correction or
other intervention moves the bridge to `needs_attention`, then back to `running` after
the same task resumes; an identity mismatch, stale evidence, or unrecoverable blocker
moves it to `blocked`.

`pending` has no real identity. Discover with `list_threads` without a client ID,
correlating project, time, path, state, and the bridge correlation ID where exposed.
On identity mismatch, stale discovery, or an untrustworthy correlation, do not guess:
record `blocked`, preserve the evidence, and ask for primary attention. Once a real
`threadId` plus `hostId` is recorded, that pair is immutable for this bridge.

Use bounded `wait_threads` monitoring for `ready`/`running` tasks. Once the real
`threadId` plus `hostId` is ready, send the identity-binding envelope below to that
same task, then wait/read that same identity and require its matching `BRIDGE ACK`
before moving the bridge to `running`. On
`needs_attention`, `completed`, or `blocked`, use `read_thread` on the same real
identity when one exists and record the observed result. A pre-identity block preserves
discovery evidence and requests primary attention without attempting `read_thread`.
A wait timeout or an old handoff is stale evidence, not completion: keep the bridge
running or move it to `needs_attention`.

## Structured envelope and acknowledgement

Put this envelope in every initial packet, ready-identity binding, and correction.
Values are primary records, not child-authored replacements.

~~~text
BRIDGE ENVELOPE
BRIDGE CORRELATION ID: <immutable primary-generated ID>
BRIDGE STATE: <pending|ready|running|needs_attention|completed|blocked>
PROJECT ID: <projectId>
TASK ID: <threadId and hostId, or pending>
CLIENT THREAD ID HISTORY: <clientThreadId values or none; handle only>
PARENT TASK: <primary task reference>
BASE / WORKTREE: <observed base and path, or pending>
REQUEST KIND: <initial|identity binding|same-task correction|PR authorization>
~~~

After a ready `threadId` and `hostId` are observed, the primary sends the same envelope
to that identity with `REQUEST KIND: identity binding`. The binding message is the
explicit parent-to-task handshake; do not treat a title, preview, or creation result
alone as a bidirectional bridge. Wait and read the same identity, and do not move to
`running` until the acknowledgement matches the recorded correlation, project, and
task IDs.

The worker returns an acknowledgement before claiming completion:

~~~text
BRIDGE ACK
BRIDGE CORRELATION ID: <copied exactly>
BRIDGE STATE: <observed state>
PROJECT ID: <observed projectId>
TASK ID: <observed threadId and hostId>
CLIENT THREAD ID HISTORY: <observed history or none>
ACKNOWLEDGEMENT: <received|identity mismatch|blocked>
~~~

The primary compares the acknowledgement with its recorded envelope. A different
correlation ID, project, or real task identity is a mismatch: do not accept the
handoff or authorize a PR; mark `needs_attention` or `blocked` and investigate.

## Same-task corrections and PR boundary

Every **SAME-TASK CORRECTION** uses `send_message_to_thread` with the same recorded `threadId` and `hostId` from the bridge, includes a new envelope with `REQUEST KIND:
same-task correction`, and names exact findings and rerun checks. Then `wait_threads`
and `read_thread` that same identity again. Never create a replacement task to bypass
a correction, and never pass `clientThreadId` to `list_threads`, `wait_threads`,
`read_thread`, or `send_message_to_thread`.

Only after primary acceptance of the current diff, checks, bridge acknowledgement,
and same-task correction cycle (if any), send `PR AUTHORIZED FOR <threadId>` in a
same-identity message. This marker is authorization only after acceptance; no child
may push, create, update, or merge a PR beforehand. Record the resulting branch,
commit, and PR evidence in the bridge before accepting a dependent stack.
