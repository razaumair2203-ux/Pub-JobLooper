# Candidate onboarding

Use this mode only when a real candidate workspace is not yet signed off.
`python jl.py init` creates a blocked workspace; `--demo` is fictional testing
only.

1. Inventory the user-selected CVs, certificates, references and career notes.
   Do not sweep unrelated folders or infer facts from filenames.
2. Register each accepted source in `truth/sources.jsonl` with its SHA-256,
   kind and path. Broad narrative sources require a reviewed coverage scope
   and one disposition for every material claim.
3. Extract atomic candidate facts into `truth/anchors.jsonl`. Preserve status,
   ownership, dates, metrics, evidence references, identity lanes and external
   disclosure boundaries. A source is provenance; it is not generation truth
   until its facts are approved as anchors.
4. Reconcile contradictions and show the proposed profile, boundaries,
   protected inventory and material atomic facts to the user. Record accepted decisions in
   `truth/changelog.jsonl`; unresolved facts remain blocked or omitted.
5. Run `python jl.py check`, `python jl.py truth audit` and `python jl.py onboard status`.
6. Only after explicit user confirmation, run:

   ```text
   python jl.py onboard finalize --reviewer "NAME" --confirm-reviewed
   ```

Finalization binds the review to an exact truth digest and schedules the next
audit. Never set `ready_for_generation` directly merely to bypass onboarding;
the digest gate will still refuse generation.
