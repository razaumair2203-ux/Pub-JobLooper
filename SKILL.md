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
2. When the user supplies a job URL, do not ask them to retype fields that can
   be verified from the official page. Use dashboard URL intake: bounded direct
   extraction first, then the `intake_url` Codex fallback for blocked or
   JavaScript-only pages. Capture only when the full employer name, exact title
   and complete JD are accessible. Search snippets are not an exact JD; if both
   routes fail, ask the user to paste the advert manually. For supplied text,
   use `python jl.py ingest`. Use the unique application key returned.
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
   letter. Before submitting, ask the user to save the portal questionnaire or
   answer summary and attach it with `--screening-file`; record `not captured`
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
9. Use `python jl.py dashboard` as the applicant-facing workspace when the user
   wants to paste a JD, work with Codex, review or comment on a bundle, approve,
   find exact artefacts, record submission evidence, capture an outcome, or
   inspect KPIs. Dashboard actions must call the same deterministic CLI gates;
   never create parallel state or let chat imply approval or external portal
   submission. Its optional Codex App Server bridge handles contextual reasoning
   and surfaces every command/file approval to the user. Codex turns use the
   user's configured OpenAI service; the loopback UI itself has no analytics.
   The canonical launch stops only the authenticated prior Joblooper instance,
   starts the current installed code on the same address and opens a fresh page;
   never kill an unrelated process merely because it occupies the port.
   Read the [dashboard contract](references/dashboard.md) when changing or
   explaining its controls, journeys or claims.

Treat the dashboard as a living product: turn user feedback into a specific
journey problem and acceptance check, improve the authoritative private source,
and propagate every accepted engine/dashboard change through the sanitized
public release. Read [dashboard and repository maintenance](references/maintenance.md)
before changing dashboard modules or publishing either repository.

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
