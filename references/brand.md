# Joblooper brand system

## Positioning

Joblooper is the evidence-backed application workspace for people who want to
tailor each application without inventing experience. It turns an approved
career record and an exact job advert into reviewable documents, then preserves
what was approved, sent and observed.

The product promise is:

> Tailor every application. Invent nothing.

The promise is a control, not advertising decoration. A screen or document
that implies automatic portal submission, hidden hiring insight, an ATS score,
or invented experience is off-brand because it contradicts the product.

## Audience and voice

Write for an experienced applicant who may use English as a second language.
Use short, concrete instructions and name the action a person can take next.
Sound calm, exact and candid. Never make certainty feel exciting when the
record is uncertain.

- Say **career record**, **application check**, **documents**, **application
  history**, **verified submission**, and **observed outcome** in the UI.
- Reserve implementation terms such as `truth`, `preflight`, `bundle`,
  `ledger`, `digest`, `manifest`, and `hypothesis` for code, CLI output and
  technical documentation.
- Say **no usage tracking** when describing telemetry. Portfolio counts and
  local summaries are product analytics, so “no analytics” is inaccurate.
- Prefer “needs your review” to “warning”, and state what is missing rather
  than describing the user as failing.
- Never call evidence coverage an ATS score, probability, ranking or hiring
  prediction.

## Visual identity

The application mark is the canonical Joblooper identifier. Use
`assets/app-mark.svg` for documentation and larger surfaces,
`dashboard/app-icon.svg` for the browser icon and compact dashboard header, and
the generated `.ico` only for operating-system shortcuts. Do not redraw the
mark inside page templates.

The interface is deliberately quiet so evidence and decisions carry the visual
weight:

| Role | Dark | Light | Use |
|---|---:|---:|---|
| Evidence/action | `#4dd9e8` | `#087d91` | links, focus, current step |
| Brand accent | `#ff5a7e` | `#bd3155` | mark framing and brand promise only |
| Verified | `#6bd7a5` | `#278660` | completed, checked, ready |
| Needs review | `#f1bf69` | `#a8680c` | uncertainty and user decisions |
| Blocked | `#ff7d78` | `#bd4441` | integrity or release blockers |

Use Aptos, Segoe UI Variable, Segoe UI, then Arial. The repository does not
ship a webfont, so do not name one that browsers must silently substitute.
Body and supporting interface text must render at 12 px or larger at the
default 16 px root size. Keyboard focus must stay visible in both themes.

## Product hierarchy

The screen order communicates the brand:

1. Working applications and the next real decision.
2. Application history, including all previously applied jobs.
3. The evidence-backed promise and priority action.
4. Portfolio summaries, verified foundations, attention and optional learning.

The employer portal remains outside Joblooper. Submission controls record the
files the user says they uploaded; they never imply that Joblooper applied on
their behalf.

Brand consistency includes dialog wording, feedback decisions, empty states,
download handoffs and learning labels. Describe the amount of supporting
evidence, not how likely a guessed rejection cause is. "No CV change needed"
and "no useful lesson" are valid outcomes of the product promise.

Employer-facing CVs and letters belong to the applicant. Keep the applicant's
identity and approved content prominent; do not add Joblooper advertising or
logos to their application documents. The product mark belongs in the workspace,
browser icon, launcher and product documentation.

## Release check

Before publishing a UI or marketing asset, verify that it uses the current
promise, the canonical mark, the vocabulary above, readable type, both theme
palettes, and the explicit portal/ATS boundaries. Retire screenshots or social
graphics when their workflow labels no longer match the product.
