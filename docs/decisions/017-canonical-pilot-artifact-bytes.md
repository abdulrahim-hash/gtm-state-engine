# ADR-017: Canonical bytes for M2B pilot artifacts

## Context

ADR-016 froze a local public-data pilot and required exact file-byte attestations. Windows `core.autocrlf=true` left several pilot JSON files with CRLF working-tree bytes, while Git committed LF bytes. The selection ledger and acceptance record were generated against the Windows bytes, so Linux CI computed a different SHA-256 for the same manifest content. Fingerprint schema 1.0.0 also included the manifest byte hash indirectly in five strategy-hypothesis source references, conflating semantic identity with file transport bytes.

## Decision

The repository pins `docs/pilot/m2b/*.json` and `docs/pilot/m2b/*.csv` to `text eol=lf` in `.gitattributes`. Every hash-addressed pilot artifact has LF bytes in the working tree and Git index on supported platforms. File-byte hashes use SHA-256 of those exact bytes; no reader strips or normalizes line endings before hashing. The selection ledger, source-verification hash, and acceptance record are regenerated through the pilot tooling against the canonical files. CSVs were already LF, so their hashes and import batch identities remain unchanged.

Semantic fingerprint schema `m2b_semantic_fingerprint/1.1.0` keeps the five strategy HYPOTHESES' semantic fields and IDs, but excludes only their manifest-byte-dependent `source_reference` and `raw_payload_hash` from the semantic projection. The acceptance gate still checks those fields against the exact canonical manifest SHA and rejects stale references. Account Evidence and all other semantic records retain their existing provenance fields in the fingerprint. Schema 1.1.0 produces the same fingerprint for databases built from the old and corrected manifest bytes when the pilot semantics are identical. The first accepted corrected run establishes its new expected fingerprint. The historic schema 1.0.0 hash remains an audit record, not the current expected value.

## Consequences

- Windows and Linux checkouts present the same bytes for hash-addressed M2B artifacts, independent of `core.autocrlf`.
- Changing a manifest byte changes its exact hash and invalidates the ledger/acceptance gate. Changing a strategy hypothesis claim or account fact changes the semantic fingerprint.
- A database built with the previous CRLF manifest has stale strategy source references and must be replayed from canonical artifacts before the local pilot acceptance gate can pass.
- The market, selected accounts, source assertions, semantic as_of, Signal, State, Decision, Policy, and Action outputs are unchanged. Production isolation and the ban on external execution remain intact.

## Status

Accepted corrective decision for M2B. ADR-016 remains the historic architecture decision; this ADR supersedes only its artifact-byte and fingerprint-schema details.
