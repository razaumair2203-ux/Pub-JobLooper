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

Manage each applicant interaction as a receipt-backed touchpoint, not as a
button or conversational turn:

1. Define the expected durable output and the exact predicate that proves it.
2. Project `complete` only from that predicate; an attempted command, directory
   or chat response is not completion.
3. Keep only the first incomplete touchpoint `current`; waiting is visible but
   never added to Attention as work.
4. Define the interrupted state and one idempotent recovery action before adding
   the control to the browser.
5. Re-read the backend projection after every mutation and test success,
   refusal, repeat and interruption from that refreshed state.

The authoritative journey is Capture, Preflight, Prepare, Review, Approve,
Build, Submit and Outcome. Browser copy, active cards, job drawers, Attention
and KPIs must derive from the same backend touchpoint projection rather than
reimplementing lifecycle booleans independently.

`python jl.py dashboard` is the canonical launch command. On its fixed loopback
port it authenticates and gracefully stops the previously registered Joblooper
instance, starts the current code, and opens the same address. It must refuse to
terminate an unrelated or unverifiable service.

Every tracked code, skill, test or dashboard change has a mandatory silent live
handoff. After proportional validation and before the final user response, run
`python jl.py dashboard --port 8765`. The authenticated launcher must replace
the older instance and open the current page on that address. Compatible open
clients detect the new instance, preserve the active job/draft and reload. Do
not ask for a manual restart or mention a successful routine handoff; report
only a failed replacement.

## Upgrade and public-release sequence

1. Implement the accepted change in `Pvt-JobLooper` without editing personal
   evidence unless the change explicitly concerns that evidence.
2. Verify proportionally while iterating: use `run_checks.ps1 dashboard` (or
   `run_checks.sh dashboard`) for dashboard/bridge work, and the directly affected
   test for other narrow changes. Run the default `full` scope exactly once before
   the private commit. A full run remains mandatory when the engine, gates,
   schemas or cross-module behavior changes.
   For any new Attention state, test the row's typed route, its actual mutation
   or governed hand-off, refusal behaviour, and the refreshed projection.
3. Commit and synchronize the private repository only while its remote is still
   private and named `Pvt-JobLooper`.
4. Clone `Pub-JobLooper` into a clean temporary path. Run
   `python tools/prepare_public_release.py <clone> --apply` from the private
   source. The command refuses any target whose classification or origin is not
   the canonical public repository.
5. Inspect the public diff, confirm its generated release fingerprint and privacy
   audit, then use the `mirror` check scope. The sanitized mirror is generated
   byte-for-byte from the already fully tested private source, so repeating every
   semantic engine test adds delay without new evidence. Run the complete public
   suite when the exporter, installer, repository policy or check runner changed.
6. Commit and push the public clone as a separate new-history repository. Never
   merge, force-push or copy Git history from `Pvt-JobLooper`.

The public working tree is replaceable; its Git history and runtime data are not.
Publishing remains an explicit external action. The synchronizer prepares and
audits a working tree but never commits or pushes it automatically.

## Lean interaction budget

Route deterministic facts directly to the dashboard. Use Codex only for
contextual oversight and give each turn an explicit scope, reasoning effort and
sandbox. Small integrity explanations are low-effort, read-only and bounded;
application positioning may use higher effort because it affects output quality.
Expose elapsed time, scope and work-item count for finished turns so latency is
observable. Do not optimize by weakening truth, approval or exact-submission
controls.
