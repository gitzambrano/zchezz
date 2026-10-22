# Engine Contracts

These identifiers define stable observable requirements. Tests should cite them when a test exists specifically to protect the contract.

## Core board/search

- **CORE-01** — `board_make` followed by `board_unmake` restores the complete logical position.
- **CORE-02** — mailbox, piece bitboards, and cached occupancies describe the same pieces.
- **CORE-03** — incremental Zobrist state equals recomputation for the current position.
- **CORE-04** — legal move generation matches reference perft values.
- **SEARCH-01** — a search does not leave the caller's board modified.
- **SEARCH-02** — time/node/stop limits terminate search and return a legal `bestmove` when legal moves exist.

## UCI

- **UCI-01** — the engine completes the UCI handshake and readiness protocol.
- **UCI-02** — `stop` terminates an active infinite/ponder search and produces `bestmove`.
- **UCI-03** — documented UCI options remain present unless the public contract is deliberately revised.

## NNUE common contracts

- **NNUE-01** — incremental evaluation state agrees with a clean rebuild for the same position and network.
- **NNUE-02** — a selected profile rejects another family's NNUE magic or dimensions instead of reinterpreting bytes.

## v335 / NNU3

- **NNU3-01** — the installed file is NNU3 with file dimensions `799,256,256,64,64` and size 426,864 bytes.
- **NNU3-02** — runtime H2 compaction preserves only L3-nonzero file neurons and pads the live set to the compiled SIMD slot count (52 slots).
- **NNU3-03** — mutable accumulator and cache state is private per search thread.

## v510 / NNU4

- **NNU4-01** — HalfKP-4-Bucket feature indexing uses the documented perspective coordinate transform.
- **NNU4-02** — concat order is `[stm, opp]`.
- **NNU4-03** — a king-bucket transition invalidates the affected perspective until rebuild or lazy refresh.
- **NNU4-04** — the compact installed network is `2560 -> 48`, concat `96`, `20 -> 1`, size 248,020 bytes.

## v605 / NNU5

- **NNU5-01** — HalfKAv2-32-Bucket feature indexing combines piece type, square, and 32 king buckets per perspective.
- **NNU5-02** — SCReLU activation function is applied on layer 1 outputs.
- **NNU5-03** — a king-bucket change invalidates the accumulator perspective and triggers an AVX2-accelerated rebuild.
- **NNU5-04** — the installed network is `22528 -> 256`, SCReLU, `64 -> 1`, size 11,547,408 bytes with calibrated Dual-NNUE auxiliary head.

## SMP / delivery / evidence

- **SMP-01** — Lazy SMP helpers share the intended TT while owning thread-private search and NNUE mutable state.
- **WEB-01** — a standalone browser bundle starts without an external NNUE download.
- **REG-01** — strength-affecting promotion requires statistical game evidence; deterministic correctness alone is insufficient.
- **REG-02** — fixed-node evidence is not interchangeable with the standard 200 ms movetime strength protocol.
- **DOC-01** — documented repository commands and paths correspond to real project surfaces.
