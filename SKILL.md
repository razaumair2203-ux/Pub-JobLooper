---
name: joblooper
description: Evidence-backed, JD-tailored CV and cover-letter lifecycle for Codex. Use when a user wants to ingest a job advert, tailor an accurate application from governed career truth, review the complete CV and cover letter in chat before rendering, track the exact submitted bundle, analyse an employer response without guessing, or preserve reusable application lessons.
---

# Joblooper

Run the workflow from this skill directory and obey `repo-policy.json`. In a
`PERSONAL_PRIVATE` source, `.joblooper/` is governed personal Git data and the
repository must stay private. A `PUBLIC_SKILL` mirror keeps runtime data outside
the installed skill. Create public copies only with the sanitized-mirror
exporter and new history; never publish personal-source history.

When installing or moving the skill to another machine, follow
[installation and portability](references/installation.md). The entire checkout
must be discoverable; copying only `SKILL.md` is not a functional installation.

## Operating contract

1. Run `python jl.py doctor` and `python jl.py context` before tailoring. If
   onboarding is blocked, follow [candidate onboarding](references/onboarding.md)
   and [ground-truth governance](references/ground-truth-governance.md); obtain
   explicit user review before enabling generation.
2. Ingest the exact advert with `python jl.py ingest`. Never reconstruct an
   unavailable JD from memory. Use the unique application key returned by the
   command.
3. Run `python jl.py preflight <key>` before planning. Ask only its material
   questions, including retained risks or exact positive outcomes from
   sufficiently similar applications; if the answer adds a candidate fact,
   update and reapprove truth. Prior outcomes are context, never causal proof.
   Then run `python jl.py plan <key>` once per unchanged truth/JD/feedback state.
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
   cover letter second—in chat. Obtain explicit user sign-off on that exact
   bundle. Any change requires a new complete presentation.
6. Only after sign-off, run `approve`, then `build`. Report the absolute dated
   application-folder path and direct CV and cover-letter paths. Use `show` or
   `open`, so the user never has to hunt through internal folders. Do not call
   an approval folder a review folder.
7. Record submission with the exact sent CV and, when used, exact sent cover
   letter. Never guess a sent file.
8. On a response, use `response` and `case` to correlate the exact JD, company,
   submitted CV and submitted cover letter. If correlation is ambiguous, say
   so and stop. For rejection or ghosting, record hypotheses with `reason`;
   confidence describes evidential support, never a claimed rejection
   probability. For interview, progression or offer, retain only the observed
   outcome and exact package—never invent a success cause. Follow the protocol
   in [outcome learning](references/rejection-learning.md).

See [README.md](README.md) for commands, schemas, gates and folder layout.
When helping a person operate or onboard the system, use the concise
[user guide](USER-GUIDE.md); do not replace the approval gates with informal
chat confirmation.

## Quality gauge

- **Lean:** one governed truth load, deterministic matching/selection/rendering,
  no default web research, no parallel prose pipeline.
- **Clean:** one shallow dated folder per approved application, direct links,
  immutable submitted bundles and no circulating versions.
- **Mean:** lead with the strongest verified differentiators, bridge them to the
  employer's stated problem and remove generic material; never compete through
  hype or fabricated familiarity.
- **Accurate:** every factual line is cited, wording authority is bounded,
  ambiguity stops correlation, and freshness/hash gates fail closed.
- **Impactful:** preserve the chronological career argument, quantified outcomes
  and full-spectrum ownership while removing duplication.

Apply user feedback through the append-only feedback workflow. Promote a lesson
to a reusable rule only after its implementation and validation are recorded.
