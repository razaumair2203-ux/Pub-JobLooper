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
7. Run `run_checks.ps1` or `run_checks.sh` before committing (both delegate to
   `tools/run_checks.py`; `python -m pytest -q` runs the same checks). CI runs
   the full scope on every push.
8. After changing anything in the public allowlist, re-export the mirror.
   `python tools/check_repo.py --mirror-drift` reports when the private source
   has moved ahead of the last published mirror.

Personal runtime data is valid only when policy is `PERSONAL_PRIVATE`; it must
never cross into public work. A `PUBLIC_SKILL` checkout accepts fictional test
data only. Public development starts from a reviewed `tools/export_public.py`
mirror with new Git history.
