---
name: joblooper
description: Evidence-backed JD screening and tailored CV/cover-letter lifecycle for Codex. Use when a user wants to check a complete job advert against governed career truth without creating application state, decide whether to promote that exact screen into an application, tailor an accurate application, review the complete CV and cover letter before rendering, track exact submissions, inspect application KPIs and artefacts, analyse employer responses without guessing, or preserve reusable application lessons.
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

## Single-source integration rule

Joblooper owns candidate truth, factual JD screening, CV/cover-letter
generation, review state, release manifests, exact submitted packages and
outcome correlation. Career strategy, project, prospect or research tools may
interpret verified Joblooper outputs, but they must not become parallel gate
engines, truth stores or final-CV generators.

Use [the integration contract](references/integration-contract.md) whenever
another application needs career context. `python tools/export_context.py`
produces a versioned, digest-bound, read-only consumer packet from the same
approved truth used by generation. `python tools/jd_screen.py screen` produces a
separate read-only `joblooper.jd-screen.v1` packet for one exact complete advert
without creating application state. A strategy consumer may use verified
packets for lane selection, evidence routing, opportunity priority, positioning
and route; it may not reclassify requirements, edit the packet into truth,
approve a claim, mark a submission or render the final employer-facing CV.

Multiple local Joblooper installations may point at one candidate data root by
setting `JOBLOOPER_DATA_DIR`, but shared location is not proof of engine/schema
compatibility. Prefer `Pvt-JobLooper` as the canonical writer for the owner's
governed runtime. Treat another install as read-only unless it belongs to the
same compatible generated release lineage. The public repository itself never
stores personal truth.

Reusable JD-screening or CV-generation behavior belongs here first.
Orchestrators should refer to Joblooper's parser/matcher/section/gate/render
contracts rather than maintain their own hard-gate parser, section order,
bullet formula, ATS rules or final artefact pipeline.

## Application compiler invariant

A CV or cover-letter request is a governed **build**, not a blank-page writing task. The factual build path is:

`one exact complete JD -> current approved atomic truth -> deterministic factual screen/evidence plan -> bounded wording and selection -> line-level traceability/ownership/status/metric/boundary gates -> reviewed release`.

Conversation/model memory, old CV prose, employer copy, repository activity, README text and strategy notes may identify a locator or a question; they never authorize a candidate fact. Every employer-facing factual headline, summary sentence, highlight, skill claim and experience bullet must cite current Joblooper anchor evidence and pass the existing gates. If a requirement has no approved evidence, keep it as a gap or preflight question. Do not close it through persuasive wording.

If current approved-context export or factual screening refuses because the candidate-truth digest is stale/inconsistent, stop authoritative compilation. A profile flag, prior approval or chat confirmation must not bypass that failure; resolve the governed truth review first.

### Functional translation without title inflation

Employer-facing wording must translate specialised military/aerospace evidence into the civilian function the JD is buying while preserving factual titles and ownership boundaries. Lead with the transferable function, then retain a public platform/programme name only when it adds credibility or necessary context; unexplained acronyms must not carry the argument.

For Product Manager/Product Owner-adjacent requirements, approved lifecycle evidence may support **technical product ownership / product-lifecycle delivery** when it explicitly covers customer or operational need, requirements/change prioritisation, cross-functional delivery, trade-offs/dependencies, V&V/qualification, acceptance/operational introduction and sustainment/performance feedback. Treat this as functional equivalence or transferable evidence unless approved truth explicitly records the formal product title. Never rewrite a historical job title as `Product Manager` or `Product Owner`, and never infer Scrum backlog authority, commercial P&L/pricing, market discovery or formal product authority from systems/programme leadership alone.

## Operating contract

1. Run `python jl.py doctor` and `python jl.py context` before screening or
   tailoring. If onboarding is blocked, follow [candidate onboarding](references/onboarding.md)
   and [ground-truth governance](references/ground-truth-governance.md); obtain
   explicit user review before enabling factual screening or generation. Treat
   a current approved-context export/screen as the readiness check: a stale truth
   digest, open adopted truth change or failed approval binding blocks authoritative
   CV compilation even if an older profile field still says generation is ready.
2. Treat **opportunity screening** and **application creation** as separate
   states. A cold workspace opens on career-truth setup, and Joblooper refuses
   authoritative work until the exact candidate-truth digest is signed; never
   work around that gate by writing candidate facts from an advert or chat.

   When the user asks **“check this JD”**, **“should I apply?”** or otherwise
   explores a vacancy, obtain the complete advert from the authoritative source
   or exact pasted text, then use:

   `python tools/jd_screen.py screen <jd-file> --company "..." --title "..." --complete-advert`

   Search snippets, vacancy-card excerpts and inaccessible/partial pages are not
   complete JDs and must not receive authoritative factual screening. Screening
   creates no `work/` application, application event, CV, approval or submission
   state. It reuses Joblooper's existing deterministic parser, identity selector
   and matcher; do not invent a second match taxonomy. A hard gate remains
   unresolved when Joblooper marks `hard_gate=true` and its evidence class is not
   `DIRECT`.

   A career-strategy layer may interpret the verified screen for priority,
   positioning and route. It may not alter `DIRECT`/`TRANSFERABLE`/`PARTIAL`/`GAP`
   classifications or convert strategy notes into candidate facts.

   When the user explicitly decides to pursue, promote the **same current
   screen** with `python tools/jd_screen.py promote <screen-file>`. Promotion
   verifies current truth/engine bindings, recomputes the deterministic factual
   analysis from the embedded structured JD and copies the exact embedded advert
   bytes into normal Joblooper application state. It never fetches or reparses a
   different vacancy copy. Repeated promotion of the same screen is idempotent.

   If the user starts with an explicit application instruction and no screen
   exists, create the factual screen first, perform only the minimum strategy
   positioning needed, then promote it. Existing `ingest`/dashboard capture
   remains a governed direct application-intake route, but do not use it merely
   to inspect jobs that may be discarded.
3. After promotion/application capture, review the complete captured advert and
   confirm its company/title in the dashboard, or run `python jl.py
   confirm-advert <key> --company "..." --title "..."`. This second confirmation
   is intentional: screen completeness governs exploration; application advert
   confirmation binds the exact record being pursued before preflight.
   Preflight and planning must refuse a missing/stale confirmation.
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
   Treat registered atomic truth records as candidate ground truth; archives and
   project repositories are provenance inputs, not a runtime search corpus. Do not
   turn employer research, model memory, a consumer packet, repository advancement
   or a strategy interpretation into candidate truth. New evidence stops at truth
   intake until the candidate reviews and approves the resulting governed delta.
4. Read the evidence plan and employer-risk decision. Research employer context
   only when it can test a material selection risk; follow
   [the bounded research protocol](references/employer-context.md). If the
   decision is `LEAVE_AS_IS`, do not decorate or reword the CV.
   Apply the per-section rules in
   [section contracts](references/section-contracts.md). A high aggregate match
   is not enough: the first third of page one must make the target function and
   strongest verified JD evidence obvious before broad career history, research
   or prestige material.
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
   user wants to set up career truth, work with a promoted/captured application,
   review or comment on a bundle, approve, find exact artefacts, record submission
   evidence, capture an outcome or inspect KPIs. The dashboard opens on
   career-truth setup until truth is signed, and on working applications
   afterwards. Exploratory read-only screening may remain headless/orchestrated
   until a screen is promoted; do not manufacture dashboard application rows for
   jobs the user is only considering.

   Five rules are normative here; everything else about its controls, journeys
   and claims is defined in the [dashboard contract](references/dashboard.md),
   which you must read before changing or explaining them.

   - **One authority.** Dashboard actions call the same deterministic CLI gates.
     Never create parallel state, and never let chat imply candidate truth,
     factual-screen authority, approval or external portal submission. Codex
     turns use the user's configured OpenAI service and surface every command/file
     approval; the loopback UI itself has no usage tracking.
   - **Durable over transient.** Every lifecycle touchpoint publishes its
     expected output beside the durable state actually observed, and active
     applications stay in the first workspace below the command bar. A chat
     panel is never the only proof that work exists. Missing analysis or
     documents are labelled `not assessed` or `not created`, never implied by a
     progress message. Re-read the projection after any mutation.
   - **Retries reconcile, never duplicate.** Screen promotion reuses an identical
     existing application, Prepare reopens a current plan, Build reuses a current
     approval, Submit completes a missing ledger write from the exact existing
     receipt. A repeated action is a verified no-op or exposes one explicit
     recovery state. A failed Codex turn ends the streaming state, exposes any
     durable partial output, and offers a safe resume that re-reads the gate and
     repeats no completed mutation.
   - **Fail visibly.** Project deterministic output-gate blockers into Review,
     Evidence and Attention before sign-off; never expose approval for a bundle
     the CLI would refuse to build. If generation returns without both CV and
     cover-letter records, fail the action visibly. Treat Attention as a
     completing task inbox: every item explains why it exists and opens the
     exact control that resolves it, and no item hides another.
   - **Proportional effort.** Route deterministic facts directly and size Codex
     effort to the decision: a factual JD screen stays deterministic/read-only;
     strategic positioning and CV/JD translation may reason more deeply because
     they are explicitly advisory or reviewed before affecting an application.

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
