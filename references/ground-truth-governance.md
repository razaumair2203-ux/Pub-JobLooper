# Ground-truth governance

Candidate ground truth is the only authority for candidate claims. A JD,
employer website, old CV, recruiter email and model memory are not candidate
truth. They may identify questions or evidence sources; they cannot create a
fact.

## Intake and approval

1. Register each documentary source with its kind, path/URL, SHA-256 and review
   scope. A hash proves file identity, not truth.
2. Extract atomic candidate claims with role/date, ownership, metrics, status,
   disclosure boundary, identity lanes and three approved wording variants.
3. For a broad narrative source, disposition every material claim as `ADOPTED`,
   `DUPLICATE`, `REJECTED` or `UNRESOLVED`. Adopted/duplicate claims cite live
   anchor IDs; unresolved claims prevent sign-off.
4. Treat a candidate comment as evidence input. Record it with `jl truth
   comment`; do not copy it straight into generation authority.
5. Show the candidate the identity, sources, atomic claims, boundaries,
   protected inventory and unresolved items. Only then run `jl onboard
   finalize --reviewer <name> --confirm-reviewed`.

Finalization records a digest over profile facts, anchors, sources, boundaries,
aliases and section rules. Approval metadata and the append-only changelog are
excluded from that digest. Any later authoritative edit blocks preflight,
planning, presentation and build until the candidate reviews the new state.

## Incremental corrections

Use `jl truth comment` for additions, corrections, wording concerns and source
questions. Resolve it as:

- `REJECTED`: no truth change; record why and how that was checked.
- `ADOPTED`: record implementation and validation; generation becomes
  `NEEDS_REVIEW` even if the edit has not yet been made.

After an adopted comment, update the structured truth, run `jl check` and `jl
truth audit`, present the exact delta/inventory to the user, then finalize
again. Never mark feedback adopted merely because prose says it was addressed.

## Periodic lean audit

`jl truth audit` is read-only. It reports integrity failures, protected
inventory, exact duplicate facts, long wording variants, superseded records and
uncited sources. It proposes no automatic deletions. An unused record is a
review signal, not evidence that the career fact is unimportant.

Every truth approval schedules another audit after 90 days. An overdue audit is
visible in `doctor`; it does not erase valid truth. Integrity errors, stale
source hashes, open comments and an approval-digest mismatch fail closed.

Default protected inventory is employment chronology, all verified degrees,
professional-tier credentials, governed career highlights, and published work
when its section is active for the lane/JD. If protected inventory does not fit,
the document gate blocks; the engine does not silently omit it.
