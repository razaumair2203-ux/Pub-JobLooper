<img src="dashboard/app-icon.svg" alt="Joblooper" width="96" align="left" hspace="16">

# Joblooper

An evidence-governed job-application system that runs entirely on your own
machine. You approve one record of your career; Joblooper tailors a CV and cover
letter to a real advert using only wording you have approved, and refuses to
build anything you have not signed off.

<br clear="left">


It will not invent experience, guess at an advert it cannot read, or claim a
requirement your evidence does not cover. When something is missing it says what
is missing and stops.

## Install and run

Python 3.10 or newer is the only requirement; the engine has no third-party
runtime dependency.

```bash
git clone https://github.com/razaumair2203-ux/Pub-JobLooper.git joblooper
cd joblooper
python jl.py setup
```

`setup` is the guided first run. It explains the system, checks what your
machine has, offers to install optional components — showing the exact command
and installing nothing without your approval — creates your workspace outside
this folder, and opens the dashboard.

Everything else is optional. Joblooper works fully without them:

| Component | What it adds if present |
|---|---|
| Microsoft Word or LibreOffice | PDF export. Without it, CVs still build as DOCX (`--no-pdf`). |
| Node.js and the Codex CLI | The optional in-app assistant for reasoning about a job. |
| Git | Updating Joblooper itself. |

Use `python jl.py setup --no-install` to see the report without any offer, or
`python jl.py doctor` to re-check later. Your data is stored outside this
checkout, so updating Joblooper never touches it.

## How the whole thing fits together

```text
 1 Career truth   Review your CV and evidence into approved facts, then sign them.
                  Nothing can be generated until you do.
 2 Capture        Paste a job link. The exact advert is stored — never a summary.
 3 Confirm JD     Read the complete capture and confirm company/title.
 4 Preflight      Joblooper answers what your truth already covers and asks only
                  about real gaps. You choose: proceed with the gap recorded, or
                  stop and add evidence.
 5 Draft          CV and cover letter assembled from approved wording only.
 6 Review         You read the complete documents. Comments block sign-off until
                  they are resolved.
 7 Approve/build  Only after sign-off do DOCX and PDF files exist.
 8 Submit         You upload to the employer. Joblooper records the exact files
                  sent and their fingerprints.
 9 Outcome        Record what the employer did. Explanations stay challenged
                  hypotheses, never facts.
```

Each step refuses to run until the one before it is genuinely complete, and
every refusal names what is missing.

**What it is not.** It does not apply on your behalf, log in to any portal,
score you against other candidates, or predict a hiring decision. There is no
analytics and no account.

## Why use AI here?

When employers use AI-assisted applicant tracking and screening, candidates can
use AI too—not to trick an ATS, invent experience or spray keywords, but to make
their own process equally systematic. Joblooper turns scattered CVs, evidence,
job descriptions, decisions and feedback into one rational application
lifecycle from first review through interview, offer, rejection or withdrawal.

There is no magic score and no claim to know a hidden hiring decision. The
system preserves what was known, what was submitted and what outcome followed.
It separates employer-stated facts from hypotheses, challenges rejection ideas
over multiple passes, and surfaces materially similar prior outcomes before the
next CV is generated. The result is continuity and accountable learning rather
than starting again from chat memory.

## Reference

- **Use Joblooper:** [user guide](USER-GUIDE.md)
- **Install details and portability:** [installation](references/installation.md)
- **Codex operating rules:** [SKILL.md](SKILL.md)
- **Privacy boundary:** [SECURITY.md](SECURITY.md)
- **Contribute:** [CONTRIBUTING.md](CONTRIBUTING.md)


## First run: establish career truth

A job advert is only useful once Joblooper knows which candidate facts it is
allowed to use, so **capture is not the first action**. On a cold install the
dashboard opens on career-truth setup and refuses job capture until the exact
truth digest is signed.

`python jl.py init` creates an empty workspace blocked from generation. It never
installs a fictional identity as real data. Follow
[candidate onboarding](references/onboarding.md), review the truth with the
candidate, then explicitly finalize it:

```powershell
python jl.py init
python jl.py onboard status
python jl.py onboard finalize --reviewer "Name" --confirm-reviewed
```

`python jl.py init --demo` is only for fictional testing.

Once the digest is signed, the dashboard opens on working applications instead,
and a later audit or material truth change returns only the affected truth to
review.

## Fast path

Python 3.10+ is required; the engine has no third-party runtime dependency.
Everything below assumes signed candidate truth.

```powershell
python jl.py doctor
python jl.py check
python jl.py ingest job.txt --company "Acme" --title "Systems Manager" --url "https://example/job/123"
python jl.py confirm-advert <exact-job-key> --company "Acme" --title "Systems Manager"
python jl.py refresh-jd <exact-job-key>  # only when Cautions reports stale analysis
python jl.py preflight <exact-job-key>
python jl.py plan <exact-job-key>
python jl.py present <exact-job-key>
```

The dashboard is the preferred preflight interface. It omits requirements
already resolved by approved truth and asks for an explicit proceed/stop
decision only on remaining fit risks. Reopening it restores the same saved
state; it does not start another AI review. Chat may clarify a gap, but the
decision is saved only by the Preflight control. Headless use passes the shown
decision IDs as JSON with `preflight --user-reviewed --reviewer "Name"
--answers-file decisions.json`.

The dashboard shows internal JD-to-evidence cautions in a dedicated, upfront
**Cautions** view before employer-facing document review. It labels nearest
text matches as candidates, never counterevidence, and withdraws any prior CV
decision when the structured JD no longer matches the exact captured advert.
The governed refresh reparses that saved source and returns the application to
preflight without changing candidate truth.

`present` prints the internal caution packet first, followed by every CV
section and the full cover letter. It creates no DOCX or PDF. After the user
signs off that exact presentation:

```powershell
python jl.py approve <exact-job-key> --reviewer "Name" --all-pass --user-signoff
python jl.py build <exact-job-key>
python jl.py artifacts <exact-job-key>
python jl.py show <exact-job-key>
python jl.py open <exact-job-key> cv
```

`build` renders deterministic DOCX files. PDF conversion uses Microsoft Word
automation on Windows or headless LibreOffice on Windows, macOS and Linux.
Otherwise use `--no-pdf` and later run `python jl.py pdf <exact-job-key>`. The
CV and cover letter share one office-engine session and are verified against
approved text.

Record the exact file actually submitted:

```powershell
python jl.py submit <exact-job-key> --sent-file "<job-folder>\CV.pdf" \
  --cover-letter-file "<job-folder>\COVER-LETTER.pdf" \
  --screening-file "<saved-portal-answers.pdf>" --channel portal
python jl.py update-submission <exact-job-key> --date YYYY-MM-DD \
  --channel portal --screening-file "<late-saved-portal-answers.pdf>"
```

This records hashes; it does not contact the employer. It refuses a file outside
the application package or one that differs from the manifest. The optional
screening file is copied into the private application record and hash-bound so
a fast outcome can be investigated without reconstructing portal answers.
`update-submission` corrects user-reported metadata or attaches late evidence;
use `--screening-unavailable` when historical portal answers cannot be recovered.
It never changes the hash-bound CV or cover letter.

## Ground-truth contract

```text
.joblooper/truth/                 only generation authority
  profile.json                    identity, contact, readiness
  anchors.jsonl                   atomic facts + approved wording variants
  sources.jsonl                   provenance, hashes, review dispositions
  boundaries.json                 ownership, privacy, disclosure exclusions
  aliases.json                    reviewed matching vocabulary
  sections.json                   section contracts, order and capacity
  changelog.jsonl                 append-only truth decisions

captured JD -> match -> select -> CV + letter -> complete chat review
       -> sign-off -> dated package -> exact submission receipt
       -> employer response -> correlated case -> reasoned lessons
```

Broad narrative files are provenance, not a searchable generation corpus. Each
new or changed source must be hash-bound, reviewed, and reconciled into atomic
anchors or explicit dispositions. A hash proves that a file is unchanged; the
candidate’s review establishes whether its claims are true.

Every generation fingerprint covers authoritative truth, JD, style, relevant
engine code and feedback. Any material change makes an old plan, presentation
or approval stale. `python jl.py why-stale <exact-job-key>` names which of those
inputs actually changed, so a withdrawn approval is explainable rather than
merely asserted.

Ground-truth sign-off is separately bound to the exact authoritative truth
digest. Use `python jl.py truth comment|resolve|audit` for incremental review;
see [ground-truth governance](references/ground-truth-governance.md).

## Section rules

| Section | Deterministic rule |
|---|---|
| Header | Use the JD-selected controlled identity and reviewed contact/disclosure settings. |
| Professional summary | Use one approved positioning anchor within configured sentence and word bounds; state authority and fit without becoming a keyword list. |
| Career highlights | Preserve governed highlights once, in declared chronological order, with independently cited recognition. |
| Skills | Rank verified methods, standards and tools by JD relevance; never manufacture keywords. |
| Experience | Answer mapped requirements, preserve every role and chronology, respect role floors/caps, and avoid repeating highlights. |
| Research/publications | Preserve every eligible published record when the section is active; respect controlled/unconfirmed status. |
| Education | Render every verified degree and dates needed to close chronology. |
| Certifications/development | Preserve professional credentials; select relevant qualifications and group verified course series with full university names. |
| Core competencies | Add only useful, deduplicated, evidence-backed JD vocabulary; omit a weak band. |

The local match score is an evidence-coverage heuristic. `DIRECT`,
`TRANSFERABLE`, `PARTIAL`, `GAP` and `BEHAVIOURAL` describe captured
requirements against registered evidence; they are not ATS scores, hiring
probabilities or guarantees.

The logo is a paper-craft parrot, made by the maintainer's child and set inside
the pentagon badge. A parrot repeats what it has heard; Joblooper repeats only
what you have approved. The favicon, the header mark and the Windows icon are
all generated from that one photograph by `tools/build_app_icon.py`, and a check
fails if any of them drifts. The original photograph is not published — see
[NOTICE](NOTICE) for the copyright position.

## Gates and judgment

The deterministic build blocks:

- untraceable text or unsupported ownership/status;
- a number absent from the exact cited records;
- prohibited disclosure or sensitive identifiers;
- duplicate evidence and omitted governed highlights/roles;
- a DIRECT requirement claimed without its mapped evidence in the rendered line;
- stale feedback, presentation, sign-off or generation inputs;
- unsafe DOCX structure, DOCX/PDF text mismatch, malformed PDF or package tamper.

Contextual review is still required for relevance, specificity, contradiction,
bloat, natural ATS wording and likely recruiter objections. It may recommend a
change only when verified evidence materially improves the argument. It cannot
invent facts, guess an absent JD or treat employer research as candidate truth.

## Artefact layout

Before approval, work remains in `.joblooper/work/<app-id>/`. Approval creates
one shallow, human-readable folder:

```text
.joblooper/jobs/YYYY-MM-DD__Company__Full Job Title__ref-Reference/
  CV.docx
  CV.pdf                         when available
  COVER-LETTER.docx
  COVER-LETTER.pdf               when available
  APPLICATION-RECORD/
    JOB-DESCRIPTION.md  JD.json  MATCH.json
    CV.md  CV-ATS.txt  CV.json
    COVER-LETTER.md  COVER-LETTER-ATS.txt  COVER-LETTER.json
    EVIDENCE.md  EMPLOYER-RISK.md  GATE-AUDIT.csv
    PRESENTATION.json  APPROVAL.json  FEEDBACK.json
    MANIFEST.json  SUBMISSION.json  SCREENING-ANSWERS.*  RESPONSES.jsonl
    CASE.md  REASONING.jsonl
```

The folder root contains only employer-facing documents; provenance and state
live one level down. Submitted bundles are immutable. `python jl.py jobs` and
`.joblooper/START-HERE.md` point to the exact JD, state and absolute folder.
Commands use the unique job key, never a company-name guess.

## Application command view

Launch the dashboard at any point in the lifecycle:

```text
python jl.py dashboard
```

On Windows, install a native launcher only when you want it:

```powershell
python jl.py dashboard --install-shortcut start-menu
# use desktop or both instead; remove with --remove-shortcut
```

The browser and launcher use the same Joblooper icon. Shortcut creation is
opt-in and never initializes or copies career data.

This is also the upgrade/restart command: it stops only the authenticated prior
Joblooper instance, starts the installed code on the same loopback address and
opens the current page. Dashboard behavior is modular and ships with both
repositories; accepted improvements are authored once in `Pvt-JobLooper` and
regenerated into the privacy-audited `Pub-JobLooper` mirror. See the
[maintenance contract](references/maintenance.md).

It opens the governed application workspace on `127.0.0.1`. From there, paste
only the official job URL; Joblooper extracts the employer, exact title and
 complete advert. You then confirm the complete capture, company and title
 before preflight. A blocked or JavaScript-only page is handed to Codex, and
manual paste appears only if neither route can access the full JD. Then work
through the deterministic Preflight control, select **Generate CV & letter**
(or type the same unambiguous request in the job panel), and review the complete
CV and cover letter, save feedback, approve and build, record the exact sent
bundle plus portal-answer evidence, capture the observed outcome, inspect KPIs,
and open every known artefact without navigating folders. Every deterministic
action calls the same CLI gates and flat-file store; there is no dashboard
database, synthetic ATS score or inferred rejection cause.

Each step is receipt-backed and retry-safe. An unchanged Prepare reopens the
current review, an interrupted approval/build exposes **Finish build** without a
second approval, and an interrupted submission receipt/ledger write exposes one
exact reconciliation action. A directory or attempted command is never treated
as proof of completion.

The Attention queue is a completing task inbox rather than a warning list. It
routes directly to preflight decisions, deterministic generation, review,
feedback resolution, exact-submission metadata,
outcome correction, integrity evidence or scoped Codex work. Dates, channel and
late portal evidence can be updated after submission without modifying the
hash-bound sent files.

The optional Codex panel uses the installed Codex CLI's official App Server.
It starts only after an explicit user turn, uses the configured OpenAI service,
and stops for user approval when Codex requests a command or file change. The
private runtime stores only the job-to-thread mapping needed to resume that
Codex context after a dashboard restart; durable facts and learning still live
in governed Joblooper records. The dashboard has no analytics and cannot claim
that it submitted into a third-party
employer portal. Use `--no-open` on a headless machine or `--snapshot` for
deterministic JSON. The [persona, journeys and control contract](references/dashboard.md)
define the exact boundary.

## Employer response and learning

```powershell
python jl.py response rejection-email.txt
python jl.py outcome <exact-job-key> --status rejected --latency under_24h
python jl.py case <exact-job-key>
python jl.py reason <exact-job-key> --cause HARD_GATE --confidence 0.60 \
  --note "Leading explanation" --evidence-for "Supporting signal" \
  --evidence-against "Counter-signal" --unknown "What cannot be known"
python jl.py lessons
python jl.py metrics
```

Correlation requires an exact reference or unique company-and-role match, a
captured JD, verified package and exact submission receipt. Ambiguity stops the
workflow. Employer-stated reasons remain facts; explanations are separate,
append-only hypotheses with evidence, counter-evidence and unknowns. Only
retained, challenged lessons influence future review. Interview, progression
and offer outcomes also surface for sufficiently similar future jobs, but only
as observations of what advanced—not as claims about why it advanced.

## Repository status

`repo-policy.json` is authoritative. Joblooper has two deliberately separate
repositories. `Pvt-JobLooper` is the authoritative `PERSONAL_PRIVATE` source and
may keep governed `.joblooper/` data in
explicitly private Git. A `PUBLIC_SKILL` checkout contains no candidate runtime
data and stores each user's data outside the installed skill. Never change a
personal repository's visibility or publish its history.

Maintainers create the public edition only as a sanitized, allowlisted tree
with new Git history:

```powershell
python tools/export_public.py D:\path\to\new-Pub-JobLooper
cd D:\path\to\new-Pub-JobLooper
python tools/check_repo.py --public-tree .
git init
```

The exporter copies an allowlist, excludes candidate data and binary evidence,
checks known direct identifiers, and refuses an existing target. Human review is
still required before publishing the mirror.

## Skill installation and verification

The repository root is a complete standalone Codex skill—not merely a
`SKILL.md`. On a fresh machine, clone the entire public repository directly
into the current user-scoped discovery path:

```bash
git clone https://github.com/razaumair2203-ux/Pub-JobLooper.git "$HOME/.agents/skills/joblooper"
cd "$HOME/.agents/skills/joblooper"
python jl.py doctor
python jl.py check
```

If `CODEX_HOME` is configured, `$CODEX_HOME/skills/joblooper` is also supported.
If the checkout already exists elsewhere, run
`python tools/install_local_skill.py`; it exposes the complete checkout through
a symlink or Windows directory junction without copying it. Private Git
authentication is needed only for a private source. A public checkout
initializes separate user runtime data with `python jl.py init`.

Codex discovers a skill from its `SKILL.md` and can invoke it explicitly with
`$joblooper` or implicitly from its description. See the
[official OpenAI skill documentation](https://learn.chatgpt.com/docs/build-skills)
for current discovery behavior.

Run the complete local audit:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_checks.ps1
python tools/check_repo.py --history
```

See [SECURITY.md](SECURITY.md) for the private/public boundary. Joblooper
improves traceability and decision quality; it cannot predict recruiters or
guarantee an interview.
