# Changelog

Notable user-facing and control-boundary changes are recorded here. Internal
career data and application details never belong in this file.

## Unreleased

### Security

- Require a same-site session cookie for private dashboard reads and reject
  unrecognised Host headers before any route is served.

### Performance

- Reuse exact file digests within one coherent snapshot, cache immutable vector
  expansions safely, resolve one job for artifact access, compact JSON, and
  conditionally cache static files with ETags.

### Interface and brand

- Route unconfirmed adverts to the advert review instead of an unavailable
  application check.
- Keep submitted jobs in Applied history and out of the drafting workspace,
  including after a later outcome; a plain "I applied" report now opens exact
  sent-file recording without guessing a file.
- Make feedback available during the first full-document review, preserve
  rejected-change reasons and before/after proposals, and route objections to
  evidence review instead of treating them as generation commands.
- Treat rejection learning as optional: waiting and an unexplained rejection
  create no compulsory task, and a no-signal record never becomes a future lesson.
- Prevent a delayed review response from replacing a newer documents or download
  view after a successful build.
- Add the Joblooper brand and product-language contract, current promise,
  readable type floor, strict-CSP progress visuals, and corrected mobile layout.
- Apply the brand vocabulary to decisions, confidence, submission, feedback and
  learning surfaces while keeping employer-facing documents applicant-owned.
- Retire the obsolete LinkedIn workflow graphic from active brand assets.
- Separate preparation work from Applied history, route an explicit “I applied”
  report to exact-file recording, and keep later outcomes in the Applied view.
- Make feedback available during the first complete review, retain rejection
  reasons, and prevent delayed review responses from replacing a newer view.
- Treat rejection learning as optional: no useful signal creates no future task
  or reusable lesson.

### Integrity

- Validate a complete feedback request before retiring an approved, unsubmitted
  package.

### Verification

- Add regressions for the read boundary, Host validation, action priority,
  cache isolation, CSP compatibility, brand copy, type size and 390 px layout.
- Extend the real-browser journey through feedback rejection, renewed complete
  review, approval, DOCX downloads, exact submission recording, Applied history,
  and an outcome that produces no invented lesson.
