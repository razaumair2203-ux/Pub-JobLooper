---
name: joblooper
description: Evidence-backed, JD-tailored CV and cover-letter lifecycle for Codex. Use when a user wants to ingest a job advert, tailor an accurate application from governed career truth, review the complete CV and cover letter in chat before rendering, track exact submissions, inspect application KPIs and artefacts, analyse employer responses without guessing, or preserve reusable application lessons.
---

# Joblooper

Run the workflow from this skill directory and obey `repo-policy.json`. In a
`PERSONAL_PRIVATE` source (`Pvt-JobLooper`), `.joblooper/` is governed personal
Git data and the repository must stay private. The `PUBLIC_SKILL` distribution
(`Pub-JobLooper`) keeps runtime data outside the installed skill. Create public
copies only with the sanitized-mirror exporter and separate history; never
publish personal-source history or edit the two code lines independently.

When installing or moving the skill to another machine, follow
[installation and portability](references/installation.md). The entire checkout
must be discoverable; copying only `SKILL.md` is not a functional installation.

## Operating contract

1. Run `python jl.py doctor` and `python jl.py context` before tailoring. If
   onboarding is blocked, follow [candidate onboarding](references/onboarding.md)
   and [ground-truth governance](references/ground-truth-governance.md); obtain
   explicit user review before enabling generation.
2. Job capture is reachable only from the `TRUTH_READY` entry state. A cold
   workspace opens on career-truth setup, and `ingest`/`ingest_url` refuse until
   the exact truth digest is signed; never work around that gate by writing
   candidate facts from an advert or from chat.
   Once truth is ready and the user supplies a job URL, do not ask them to
   retype fields that can be verified from the official page. Use dashboard URL
   intake: bounded direct extraction first, then the `intake_url` Codex fallback
   for blocked or JavaScript-only pages. Capture only when the full employer
   name, exact title and complete JD are accessible. Search snippets are not an
   exact JD; if both routes fail, ask the user to paste the advert manually. For
   supplied text, use `python jl.py ingest`. Use the unique application key
   returned.
3. Review the complete captured advert and confirm its company/title in the
   dashboard, or run `python jl.py confirm-advert <key> --company "..." --title
   "..."`. Preflight and planning must refuse a missing/stale confirmation.
   Then run `python jl.py preflight <key>` before planning. It must resolve the exact
   JD against approved truth first: omit facts already answered, then present
   only remaining known gaps or application decisions. Record each decision in
   the dashboard Preflight control; chat is optional for clarification and is
   never the answer store. `Proceed with recorded gap` creates no candidate
   fact. `I have new evidence` stops generation until truth is updated and
   reapproved. For headless CLI use, pass the same per-item decisions with
   `--answers-file`; a free-text acknowledgement cannot resolve the gate.
   Retained risks or exact positive outcomes from sufficiently similar
   applications remain context, never causal proof.
   Then run `python jl.py plan <key>` once per unchanged truth/JD/feedback state.
   In the dashboard, **Save & generate CV + letter** performs these two governed
   transitions in sequence, and **Generate CV & letter** runs the same
   deterministic plan after a completed preflight. Routine generation must not
   depend on a conversational stream completing; use Codex for contextual
   review and material improvement decisions.
   A current plan exists only when all governed plan records and the final plan
   receipt agree with the exact preflight decision digest. Repeating generation
   against that unchanged state reopens the current review; it must not create
   another version or restart contextual reasoning.
   Treat registered atomic truth records as
   candidate ground truth; archives are provenance inputs, not a runtime search
   corpus. Do not turn employer research into candidate truth.
4. Read the evidence plan and employer-risk decision. Research employer context
   only when it can test a material selection risk; follow
   [the bounded research protocol](references/employer-context.md). If the
   decision is `LEAVE_AS_IS`, do not decorate or reword the CV.
   Apply the per-section rules in
   [section contracts](references/section-contracts.md).
5. Run `python jl.py present <key>` and place its complete output—CV first,
   cover letter second—in chat, or expose the same complete content in the
   dashboard Review tab. Obtain explicit user sign-off on that exact bundle.
   Any change requires a new complete presentation.
6. Only after sign-off, run `approve`, then `build`. Approval and build are
   separate durable touchpoints: an approval folder without a verified manifest
   is **build incomplete**, never a sendable package. Resume it with `build`
   against the existing approval; do not approve again. Report the absolute dated
   application-folder path and direct CV and cover-letter paths. Use `show` or
   `open`, so the user never has to hunt through internal folders. Do not call
   an approval folder a review folder.
7. Record submission with the exact sent CV and, when used, exact sent cover
   letter. Before submitting, ask the user to save the portal questionnaire or
   answer summary and attach every saved page with repeated `--screening-file`;
   record `not captured`
   rather than reconstructing unavailable answers. Never guess a sent file.
   Use `--confirm-external` only for a retrospective, explicit user confirmation
   where every selected sent file still matches its approved manifest; it does
   not repair a modified package.
8. On a response, use `response` and `case` to correlate the exact JD, company,
   submitted CV and submitted cover letter. If correlation is ambiguous, say
   so and stop. For rejection or ghosting, record hypotheses with `reason`;
   confidence describes evidential support, never a claimed rejection
   probability. For interview, progression or offer, retain only the observed
   outcome and exact package—never invent a success cause. Follow the protocol
   in [outcome learning](references/rejection-learning.md). Use `metrics` for
   descriptive lifecycle KPIs; never present them as hiring probabilities.
9. Use `python jl.py dashboard` as the applicant-facing workspace whenever the
   user wants to set up career truth, capture a JD, work with Codex, review or
   comment on a bundle, approve, find exact artefacts, record submission
   evidence, capture an outcome or inspect KPIs. The dashboard opens on
   career-truth setup until truth is signed, and on working applications
   afterwards.

   Five rules are normative here; everything else about its controls, journeys
   and claims is defined in the [dashboard contract](references/dashboard.md),
   which you must read before changing or explaining them.

   - **One authority.** Dashboard actions call the same deterministic CLI gates.
     Never create parallel state, and never let chat imply candidate truth,
     approval or external portal submission. Codex turns use the user's
     configured OpenAI service and surface every command/file approval; the
     loopback UI itself has no analytics.
   - **Durable over transient.** Every lifecycle touchpoint publishes its
     expected output beside the durable state actually observed, and active
     applications stay in the first workspace below the command bar. A chat
     panel is never the only proof that work exists. Missing analysis or
     documents are labelled `not assessed` or `not created`, never implied by a
     progress message. Re-read the projection after any mutation.
   - **Retries reconcile, never duplicate.** Prepare reopens a current plan,
     Build reuses a current approval, Submit completes a missing ledger write
     from the exact existing receipt. A repeated action is a verified no-op or
     exposes one explicit recovery state. A failed Codex turn ends the streaming
     state, exposes any durable partial output, and offers a safe resume that
     re-reads the gate and repeats no completed mutation.
   - **Fail visibly.** Project deterministic output-gate blockers into Review,
     Evidence and Attention before sign-off; never expose approval for a bundle
     the CLI would refuse to build. If generation returns without both CV and
     cover-letter records, fail the action visibly. Treat Attention as a
     completing task inbox: every item explains why it exists and opens the
     exact control that resolves it, and no item hides another.
   - **Proportional effort.** Route deterministic facts directly and size Codex
     effort to the decision: a small integrity explanation stays bounded and
     read-only; CV/JD positioning may reason more deeply because it changes
     application impact.

   The canonical launch stops only the authenticated prior Joblooper instance,
   starts the current installed code on the same address and opens a fresh page;
   never kill an unrelated process merely because it occupies the port.
   After changing tracked Joblooper source, skill, test or dashboard files,
   validate the affected behavior. If a dashboard is running and the change
   affects it, offer to relaunch with `python jl.py dashboard --port 8765` and
   say so in the final response — do not hot-replace a server the user may be
   using without telling them. Never leave older code as the visible page
   without saying that it is stale.

Treat the dashboard as a living product: turn user feedback into a specific
journey problem and acceptance check, improve the authoritative private source,
and propagate every accepted engine/dashboard change through the sanitized
public release. Read [dashboard and repository maintenance](references/maintenance.md)
before changing dashboard modules or publishing either repository.

See [README.md](README.md) for commands, schemas, gates and folder layout.
When helping a person operate or onboard the system, use the concise
[user guide](USER-GUIDE.md); do not replace the approval gates with informal
chat confirmation.

## Write for the person, not the system

Everything a user reads must be plain language. Many are applying for jobs in a
second language, and text they cannot parse quickly they will click past —
which defeats a correct signal just as thoroughly as not showing it. Use short
sentences rather than stacked clauses, ordinary words rather than technical
ones, and address the user directly.

Never surface an internal name: not a cause code, not a status such as
`RETAINED_PLAUSIBLE`, and not words like hypothesis, disposition, digest,
artefact, provenance or deterministic. Those belong in the record, not on
screen.

This matters most for a retained lesson. It is quoted back months later at the
exact moment the user is deciding whether to apply, so write it as one plain
sentence about what to do differently next time, not as an instruction to the
engine. "Ask about the visa before applying" carries; "preflight must separate
technical lifecycle fit from direct customer, regulatory and localisation fit"
does not.

Apply user feedback through the append-only feedback workflow. Rejected feedback
requires a rationale; adopted feedback cannot be marked resolved until a changed
plan digest proves that it was implemented. Promote a lesson to a reusable rule
only after its implementation and validation are recorded.

The review judgment aids — Lean, Clean, Mean, Accurate, Impactful — are in
[the quality gauge](references/quality.md). They guide review; they are not
gates and cannot authorize a claim the deterministic gates would refuse.
