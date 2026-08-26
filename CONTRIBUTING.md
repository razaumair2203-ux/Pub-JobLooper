# Contributing

The source policy is declared in `repo-policy.json`. Keep the lifecycle
deterministic, evidence-preserving and portable.

1. Do not push until the private remote and intended diff are verified.
2. Use only fictional data in tests, examples and reusable documentation.
3. Add a regression for every gate, matcher, store or release-control change.
4. Preserve submitted application folders and unrelated user changes.
5. Keep truth-schema changes backward compatible or provide a migration.
6. Prefer the standard library; a dependency must justify its portability and
   audit cost.
7. Run `run_checks.ps1` or `run_checks.sh` before committing.

Personal runtime data is valid only when policy is `PERSONAL_PRIVATE`; it must
never cross into public work. A `PUBLIC_SKILL` checkout accepts fictional test
data only. Public development starts from a reviewed `tools/export_public.py`
mirror with new Git history.
