# Dashboard and repository maintenance

Joblooper has one authored code line and two deliberately different repositories:

- `Pvt-JobLooper` is the authoritative private source. It may contain governed
  personal truth and application artefacts and must remain private.
- `Pub-JobLooper` is a generated public distribution. It contains the same
  installable engine, skill, dashboard and fictional examples, but no personal
  runtime, personal artefacts or private Git history.

Never implement a feature independently in both repositories. Make and test the
change once in `Pvt-JobLooper`, then regenerate `Pub-JobLooper` with the sanitized
export. This prevents functional drift while keeping the privacy boundary real.

## Living dashboard contract

Treat dashboard feedback as product evidence, not an automatic code instruction.
Clarify the user obstacle and an observable acceptance condition; change only what
improves that journey. Keep these module boundaries:

| Responsibility | Module |
|---|---|
| Read-only lifecycle projection and loopback API | `core/dashboard.py` |
| Authenticated single-instance restart | `core/dashboard_runtime.py` |
| Allowlisted deterministic mutations | `core/dashboard_actions.py` |
| Bounded official job-link extraction | `core/job_fetch.py` |
| Optional contextual Codex bridge | `core/codex_bridge.py` |
| Browser structure, behavior and presentation | `dashboard/index.html`, `dashboard/app.js`, `dashboard/styles.css` |

Do not add a second database or bypass the CLI gates. Add or extend the module
that owns the behavior, its invariant test, and the relevant user-facing copy.

`python jl.py dashboard` is the canonical launch command. On its fixed loopback
port it authenticates and gracefully stops the previously registered Joblooper
instance, starts the current code, and opens the same address. It must refuse to
terminate an unrelated or unverifiable service.

## Upgrade and public-release sequence

1. Implement the accepted change in `Pvt-JobLooper` without editing personal
   evidence unless the change explicitly concerns that evidence.
2. Run `run_checks.ps1` on Windows or `run_checks.sh` on macOS/Linux. A dashboard
   change must pass `tests/test_dashboard.py` and installability checks.
   For any new Attention state, test the row's typed route, its actual mutation
   or governed hand-off, refusal behaviour, and the refreshed projection.
3. Commit and synchronize the private repository only while its remote is still
   private and named `Pvt-JobLooper`.
4. Clone `Pub-JobLooper` into a clean temporary path. Run
   `python tools/prepare_public_release.py <clone> --apply` from the private
   source. The command refuses any target whose classification or origin is not
   the canonical public repository.
5. Inspect the public diff, run the complete checks in that clone, and confirm
   its generated release fingerprint and privacy audit.
6. Commit and push the public clone as a separate new-history repository. Never
   merge, force-push or copy Git history from `Pvt-JobLooper`.

The public working tree is replaceable; its Git history and runtime data are not.
Publishing remains an explicit external action. The synchronizer prepares and
audits a working tree but never commits or pushes it automatically.
