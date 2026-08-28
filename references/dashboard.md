# Dashboard product and control contract

## Applicant persona

The primary user is an experienced applicant pursuing a small number of
high-value roles. They want to apply through one surface and should never need
to know application keys, hashes, commands, release names or folder internals.
They are willing to review evidence and make decisions, but expect the system to
remember exact artefacts and to refuse unsupported claims.

The workspace must answer these questions without reconstruction:

1. What job am I working on, and what is the next real decision?
2. What exact JD, CV, letter and portal evidence belong to it?
3. What has Codex proposed, what did I approve, and what remains blocked?
4. What was submitted and what outcome was observed?
5. Which rejection explanations are only best guesses, and which lesson—if any—
   survived evidence challenge for future preflight?

## Product boundary

The dashboard is a governed front door over the existing Joblooper store and
CLI. It is not a second application engine.

- **Deterministic controller:** intake identity, truth readiness, preflight,
  presentation freshness, feedback invalidation, sign-off, document build,
  manifest verification, exact submission binding, response correlation and
  KPI calculation.
- **Codex:** contextual questioning, JD/profile reasoning, application planning,
  drafting through the governed pipeline, feedback discussion and hypothesis
  challenge. Codex cannot turn a chat statement into candidate truth, approval,
  external submission or an employer-stated cause.
- **User:** supplies missing facts, reviews the complete CV and cover letter,
  explicitly signs off, uploads to the employer portal, selects the exact files
  actually sent, and labels observations.
- **Employer portal:** remains external. Joblooper may open the official advert
  and preserve user-supplied portal evidence; it never claims it clicked Submit.

All dashboard mutations call allowlisted CLI actions. There is no dashboard
database and no browser-supplied filesystem path. Governed feedback, truth,
artefacts, outcomes and reasoning remain in the same append-only or hash-bound
records used by the CLI.

## Essential journey controls

| Journey step | Applicant interaction | Controller and proof of completion | Fail-closed behaviour |
|---|---|---|---|
| Capture | Paste the official job URL; use manual fields only after both access routes fail | Bounded URL extractor, then scoped Codex URL fallback, then deterministic `ingest`; when both access routes fail, the manual-paste panel reopens automatically with the URL preserved and the first missing field focused | Private-network URLs, blocked pages, incomplete content and search-snippet reconstruction are refused; advert prose is never candidate truth |
| Preflight | Review only unresolved fit decisions; use Codex only when a gap needs explanation | Deterministic JD/truth match plus per-item governed `preflight` answers | Resolved facts are not re-asked; new evidence stops for truth review; chat cannot complete the gate |
| Prepare | Discuss positioning and generate through the existing pipeline | Truth/JD/feedback fingerprints plus `match`, `cv`, `cover-letter` and risk records | Stale or unapproved truth, hard gates or unanswered questions stop generation |
| Review | Read the full CV and cover letter in the Review tab; add scoped comments | Exact presentation digest and append-only feedback | Open feedback or any content change makes presentation/sign-off stale |
| Approve | Tick exact-bundle confirmation and name the reviewer | Approval digest bound to the current presentation | Chat approval, partial review or stale content is refused |
| Build | Use Approve & build after sign-off | Dated human-readable folder, verified manifest, direct CV/letter links | Build gate errors remain visible; no silent force path is exposed |
| Submit | Upload externally, select exact sent CV/letter, optionally attach portal answers | Submission receipt with hashes; screening evidence copied and hash-bound | Browser cannot invent paths; Joblooper never claims external submission |
| Correct record | Open **Update dates & portal evidence** from Attention or the job workspace | Submission date/channel and late portal evidence are appended to the existing receipt and ledger; exact sent-file hashes remain unchanged | Future dates, dates after the response, unverifiable submissions and silent evidence reconstruction are refused; permanently unavailable historical answers are labelled explicitly |
| Outcome | Paste exact response or record observation/date/timing | Response hash and exact application correlation, or explicit direct outcome | Ambiguous job correlation stops; absent reason remains `none provided` |
| Learn | Discuss competing explanations with Codex and save substantive revisions | Reasoning log with evidence, counterevidence, unknowns and status | Confidence means evidence support, never probability; no explanation becomes fact automatically |

## Interaction model

### Persistent working-applications surface

The first content below the command bar is the working-applications surface,
not portfolio analytics. A successful URL capture creates or refreshes one card
there immediately. Closing Codex, refreshing the browser or completing a turn
must not make the work appear to vanish.

Each active card must expose, without opening a folder:

- exact company, role, reference, lifecycle state and last durable activity;
- all seven gates and the current next action;
- whether evidence coverage and gaps are assessed, with an explicit statement
  that coverage is not an ATS score;
- whether the CV and cover letter exist, plus direct artefact counts and links;
- recorded and unresolved user comments;
- direct controls for the next gate, the job workspace and captured JD.

An absent output is a visible state, not a blank panel: after JD capture the
card shows the deterministic evidence/gap assessment and says that the CV and
cover letter have not been created. Portfolio KPIs, lifecycle charts and learning remain secondary below
this operational surface.

### Touchpoint visibility contract

| User touchpoint | What remains visible afterwards | Required next control |
|---|---|---|
| Paste URL | Active card, exact source-JD links, evidence/gap assessment and captured timestamp | Review deterministic preflight decisions |
| Direct extraction blocked | Codex tries only the same official URL; if capture succeeds it binds the job and opens the same deterministic control used by direct intake | Preflight decisions; otherwise the automatically reopened manual form |
| Preflight incomplete | `Preflight` gate open; resolved facts omitted; remaining known gaps and their consequences visible | Save proceed/stop decisions in Preflight; chat is optional clarification |
| Codex interrupted | `Thinking` ends; current governed files are re-read; registered artefacts and their absence remain visible and the failure is labelled without assuming completion | Resume safely from the next incomplete contextual task or open the application workspace |
| Plan generated | Evidence coverage, requirement classes, hard gaps, risk record and draft availability | Open complete CV-and-letter review |
| User reviews | Exact complete bundle remains readable in the Review tab | Add a scoped comment or mark the complete bundle presented |
| User comments | All open and resolved comments remain attached to the job; open items block approval | Resolve, regenerate if adopted, then re-present |
| User approves/builds | Direct verified CV and cover-letter links appear in the same workspace | External upload and exact submission record |
| User submits | Exact sent files, date, channel and portal-answer evidence state remain visible | Await or record observed outcome |
| User records outcome | Employer observation remains separate from hypotheses and learning | Discuss evidence only when a decision is still useful |

### Portfolio surface

- Shows in-progress, submitted, progressed and rejected counts.
- Separates evidence-control KPIs from observed outcomes.
- Surfaces the next missing control, not an endless instruction to discover an
  unknowable rejection cause.
- Makes sample size and employer concentration visible before trend claims.

### Attention queue

Attention is the applicant's task inbox, not a warning feed. Every row states
why input is needed and ends in one valid control. Merely waiting for an employer
is visible in the application ledger but is not a task.

| Queue state | Direct interaction | Successful output |
|---|---|---|
| Captured JD | Review preflight decisions | Per-gap proceed/stop decisions or a verified no-decision preflight |
| Review ready | Open complete review | Current CV and cover letter, then feedback or sign-off |
| Open feedback | Resolve feedback | Append-only adopted/rejected decision with rationale and validation |
| Approved bundle | Open submission desk | Hash-bound exact-submission receipt |
| Missing submission metadata | Update record | Corrected date/channel, attached late portal evidence, or explicit `unavailable` state |
| Missing outcome date | Update outcome | Existing status, timing and reason prefilled; corrected observation retained |
| Integrity failure | Inspect artefacts | Exact failed control and artefact are visible; downstream correction remains blocked |
| Ground-truth integrity failure | Review options | Exact source/digest error and safe choices open instantly; a bounded low-effort, read-only Codex discussion is optional |
| Progressed/rejected reasoning | Work with Codex | Fact/hypothesis/unknown separation and, only when justified, a retained lesson |

Queue generation and action routing are tested together. A new queue kind is
incomplete until its direct interaction, failure state and refreshed output have
all been specified and covered by a regression test.

### Job workspace

- Overview shows the seven gates: JD, preflight, plan, review, approval, build
  and submission.
- Artefacts resolve to allowlisted files inside the configured data root.
- Review displays the exact complete CV and cover letter before sign-off.
- Evidence labels coverage as a local heuristic, never an ATS score.
- Outcome displays employer facts before hypotheses.
- Timeline shows immutable lifecycle events.
- Comments shows both open and resolved review feedback with implementation and
  validation, so chat suggestions do not disappear into conversation history.

### Codex panel

- Keeps one conversation context per visible job during the dashboard session.
- Sends a scoped intent and exact job key through the official Codex App Server.
- Uses explicit proportional profiles: bounded integrity and submission checks
  are low-effort/read-only, ordinary questions are medium, and application
  positioning alone receives high effort. Finished turns show elapsed time,
  scope and work-item count rather than hiding latency.
- Uses `approvalPolicy=on-request`, `approvalsReviewer=user` and the workspace
  sandbox. Command and file-change requests appear in the dashboard and support
  only allow-once, decline or cancel.
- Does not store credentials. Authentication and model conversation history are
  owned by the installed Codex CLI. A small private index maps each job to its
  Codex thread so the backend can resume context after a dashboard restart.
- Chat display is conversational context, not system memory. Anything that must
  survive or influence a future application is saved through truth, feedback,
  submission, outcome or reasoning records.
- The selected job always shows registered clickable artefacts above the
  conversation and explicitly says when the CV or cover letter does not exist;
  agent prose never substitutes filesystem paths for these controls.
- A failed or disconnected turn is terminal, not a perpetual streaming state.
  The panel shows a concise interruption, refreshes the deterministic projection
  and offers a deliberate safe resume that first re-reads the job and repeats no
  completed mutation. A prepared preflight-decision file is a visible partial
  artefact, not proof that preflight was reviewed.
- A free-form job-scoped request to prepare, generate or tailor a CV/application
  receives the application-work execution profile; ordinary questions remain
  proportional. This routing changes reasoning effort, never factual authority.

### Live-version continuity

The session exposes a bounded dashboard instance identifier. An open client
polls that identity; after an authenticated replacement it preserves the active
job and unsent Codex draft, reloads current assets, and restores that context.
The canonical post-change launch also opens the current address so a client
that predates this capability cannot remain the only visible page.

## Rejection language contract

An automated rejection without an employer-stated reason establishes only the
status and observed timing. The dashboard may show retained or open hypotheses,
but the default action is:

- use a retained best guess as a future preflight question;
- leave unresolved alternatives unknown; and
- improve evidence capture for future submissions.

It must not say “continue the evidence challenge” after the useful reasoning
passes are complete, imply that the actual cause can be discovered, or suggest
that an evidence-support percentage is the employer's rejection probability.

## Security and privacy

- HTTP binds to `127.0.0.1`, uses `no-store`, rejects framing and loads no CDN or
  third-party front-end dependency.
- State-changing requests require a random session token plus exact same-origin
  header. Bodies are bounded; screening uploads are allowlisted and limited to
  8 MB.
- The browser selects artefact IDs; the server resolves exact paths from a
  private registry and the CLI re-verifies the package.
- The dashboard has no analytics. An explicit Codex turn uses the user's
  configured OpenAI service; this must not be described as offline processing.
- External portal automation is not enabled.

## Visual system

Use a calm aerospace-workspace tone: ink/navy surfaces, cyan for active work,
green for verified state, amber for unknown/review and red only for observed
negative outcomes or integrity failures. Native SVG/CSS is intentional: the
small categorical dataset does not justify Chart.js or D3, and avoiding a CDN
improves speed, privacy and public-skill portability.

Responsive layouts must preserve all actions at desktop, tablet and phone
widths. Drawers and the Codex panel trap keyboard focus; dialogs use native
modal behaviour; colour is never the only state cue.

## Known external wall

Employer portals vary, require authentication, may present dynamic screening
questions and may forbid automation. The safe journey therefore stops at a
verified sendable bundle, opens the official portal for the user, then records
the exact files and optional saved screening evidence after the user uploads.
This is a deliberate authority boundary, not an unfinished dashboard feature.

## Acceptance checks

- Every job appears once and all lifecycle counts reconcile to the ledger.
- A new JD can be captured without a command line and is immediately visible.
- Working applications are above analytics and show real gate state, absent
  outputs, evidence/gaps, comments and direct artefact controls.
- Closing or completing a Codex intake turn cannot hide the captured job; a
  Codex URL fallback binds the new job and opens the same deterministic preflight.
- Reopening Preflight returns the existing decision state and never starts a
  duplicate Codex turn; every legitimate decision is answerable in the dialog.
- A failed stream cannot remain labelled `Thinking`; retry inputs and any
  durable partial artefact survive, and three failed task polls stop rather than
  creating an infinite reconnect loop.
- Replacing the dashboard changes its instance identity; a loaded compatible
  client reloads automatically and restores its active job/draft.
- URL-only intake extracts structured `JobPosting` fields, rejects private
  network targets and falls back to Codex before requesting manual entry.
- A scoped Codex turn reaches the App Server; an unavailable service shows a
  real error instead of a simulated answer.
- Feedback invalidates stale presentation/approval through the existing engine.
- Every Attention row has a typed route, explanatory detail and a completing
  interaction; waiting-only applications do not become false tasks.
- Submission dates, channel and late portal evidence can be corrected without
  changing the exact sent CV/letter; each correction is event-traced.
- Open feedback can be resolved from its queue row, with explicit rationale and
  validation, instead of opening an unrelated comment form.
- Ground-truth integrity errors override a stale `ready` sign-off, show their
  exact cause and become a blocking system-level Attention item; evidence is
  never silently re-hashed or re-trusted.
- Approval cannot precede complete presentation or bypass open feedback.
- Submission accepts only verified package artefacts and preserves optional
  screening evidence with a digest.
- Outcome capture preserves exact employer text when supplied and never invents
  a stated reason.
- Rejection facts, retained best guesses, alternatives and unknowns remain
  visually and semantically separate.
- The fictional starter, empty workspace and public mirror work without network
  or third-party UI dependencies; live Codex integration is tested separately.
