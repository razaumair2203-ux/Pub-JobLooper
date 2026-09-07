# Joblooper user guide

Joblooper turns one user-approved career record and one captured job
description into a traceable CV and cover-letter package. It does not search
old CVs while drafting and does not create employer-facing files before you
approve the complete text in chat.

**The dashboard (`python jl.py dashboard`) is the primary surface.** Everything
below can be done there without knowing an application key, a hash or a folder
path. The commands are shown because they are the recovery and automation
surface — useful when something is interrupted, when you are scripting, or when
you want to see exactly which gate refused — not because you need them.

The dashboard has two entry states. Until your career truth is signed it opens
on truth setup and will not capture a job, because Joblooper will not tailor an
application against facts you have not reviewed. Once signed, it opens on your
working applications.

## 1. Install and initialize

Follow [installation and portability](references/installation.md). In a public
checkout, initialize a private runtime outside Git:

```text
python jl.py init
python jl.py doctor
```

`doctor` explains anything still needed. `init --demo` is fictional testing
only and must not be used as a real profile.

## 2. Build and approve ground truth

Give Codex only the CVs, certificates, references and comments you want it to
review. Codex registers evidence, extracts atomic facts, records conflicts and
shows you the proposed truth. Generation remains blocked until you sign off:

```text
python jl.py check
python jl.py truth audit
python jl.py onboard status
python jl.py onboard finalize --reviewer "YOUR NAME" --confirm-reviewed
```

Add later feedback with `truth comment` and resolve it as adopted or rejected.
An adopted fact or any material truth edit invalidates the old approval and
requires a fresh review. Periodic audits identify duplicates, stale sources,
oversized variants and protected facts without silently deleting anything.

## 3. Tailor an application

Provide the exact job description, company, title and URL/reference. Joblooper
will not guess an unavailable advert.

```text
python jl.py ingest job.txt --company "Company" --title "Job title" --url "https://example/job/ref"
python jl.py confirm-advert <exact-job-key> --company "Company" --title "Job title"
python jl.py preflight <exact-job-key>
python jl.py plan <exact-job-key>
python jl.py present <exact-job-key>
```

The dashboard first displays the complete immutable advert and asks you to
confirm its company and title. Only then use **Preflight review** for the remaining decisions. Joblooper
has already checked approved truth, so resolved facts do not appear again.
Choose **Proceed with recorded gap** to continue without inventing the missing
experience, or **I have new evidence** to stop and update ground truth. Chat is
available to clarify a gap, but it is not where the decision is stored.
Reopening Preflight restores the same application state. `present` then shows
the entire CV, cover letter, omission disclosure and rejection-risk assessment
in chat. No DOCX or PDF exists yet.

### When a gap is something you actually have

Preflight will sometimes flag a requirement you *can* meet — the evidence simply
was never added to your record. Choose **I have evidence that closes it** and say
in one line what it is.

Joblooper will not write that into your CV for you, and neither will Codex.
Nothing reaches a CV except facts you have reviewed and signed, which is what
stops the system inventing experience. So this opens your career-truth
workbench instead, and the path is:

1. Upload the document that proves it — a certificate, an older CV, a reference.
2. Go through the facts Joblooper reads out of it, keeping, editing or rejecting
   each one.
3. Sign your record again.

You are then returned to the exact question that sent you there, and the CV can
be rebuilt with the new evidence available to it. It takes a few minutes the
first time. It is also the reason nothing in your CV can be something you never
approved.

If the gap is real — you genuinely do not have what they asked for — choose
**Proceed with recorded gap** instead. The application continues, the gap stays
visible in Cautions, and nothing is claimed on your behalf.

## 4. Approve and find the files

After you approve the exact presentation:

```text
python jl.py approve <exact-job-key> --reviewer "YOUR NAME" --all-pass --user-signoff
python jl.py build <exact-job-key>
python jl.py show <exact-job-key>
python jl.py open <exact-job-key> folder
```

The dated folder is named with creation date, company, full job title and job
reference. Its root contains only the sendable CV and cover letter; evidence,
JD, gates and manifests live in `APPLICATION-RECORD/` one level below.
If document rendering stops after approval, the dashboard shows **Finish build**
and reuses the saved approval. Files are submit-ready only after the manifest
verifies; do not approve a second time.

## 5. See the whole portfolio

```text
python jl.py dashboard
```

On Windows, optionally install the branded launcher with `python jl.py dashboard
--install-shortcut start-menu` (or `desktop` / `both`). Remove only those links
with `--remove-shortcut`; career data is not touched.

Run the same command after an upgrade. It replaces only the verified previous
Joblooper dashboard, reuses `http://127.0.0.1:8765/`, and opens the current page.
If another application owns the port, Joblooper refuses to terminate it.

The local workspace answers what is in progress, what needs attention, which
exact files belong to each job, which outcomes were observed, and which
rejection lessons survived challenge. It is also the simplest front door:
paste the official job URL, let Joblooper extract the employer, title and full
advert, confirm that exact capture, resolve the deterministic preflight decisions, select **Generate CV &
letter**, and review the
complete CV and letter, add comments, approve and build, record the exact sent
files and portal answers, and paste the employer response. The same CLI gates
control every action; the dashboard does not maintain a second database.

Use **Attention queue** as the task inbox. A row opens the exact required
interaction: preflight decisions, complete review, feedback resolution,
finish-build or submission-record recovery, submission, record correction,
outcome correction, integrity evidence or scoped Codex reasoning. Applications
merely awaiting an employer response stay visible in the ledger without
becoming false tasks.

After submission, choose **Update dates & portal evidence** from Attention or
the job workspace to correct the submission date/channel, attach saved portal
answers later, or explicitly record that historical answers are unavailable.
This appends an audit event; it never changes the CV or cover letter hashes.

If the site blocks normal access or requires JavaScript, the URL is handed to
Codex automatically. Only when Codex also cannot retrieve the complete official
advert does the workspace ask you to paste the company, title and JD manually.
It never rebuilds a missing advert from search snippets.

The UI binds only to `127.0.0.1` and has no analytics. When you explicitly
message Codex, the installed Codex CLI uses your configured OpenAI service.
Each job resumes its private Codex thread when available, but only saved truth,
feedback, outcome and reasoning records count as durable system memory. Command
and file-change requests stop for your approval. Upload to the employer
portal remains your action; the dashboard records exactly what you say was sent.
Stop the local server with `Ctrl+C`.

## 6. Record submission and responses

Record the exact submitted files so a later response can be correlated without
guessing:

```text
python jl.py submit <exact-job-key> --sent-file "<path-to-CV>" --cover-letter-file "<path-to-letter>" --screening-file "<portal-page-1>" --screening-file "<portal-page-2>" --channel portal
python jl.py update-submission <exact-job-key> --date YYYY-MM-DD --channel portal --screening-unavailable
python jl.py response rejection-email.txt
python jl.py case <exact-job-key>
```

When there is no usable email content, record the outcome directly. Preserve a
reported timing band without inventing an exact date:

```text
python jl.py outcome <exact-job-key> --status rejected --latency under_24h
python jl.py metrics
```

`metrics` reports evidence-capture and observed-outcome KPIs with a small-sample
warning. They are descriptive controls, not ATS scores or hiring probabilities.

Rejection explanations remain hypotheses. Joblooper requires competing causes,
counterevidence, unknowns and multiple substantive reasoning passes before a
lesson can be retained. Only an employer-stated reason may be marked confirmed.
Interview, progression and offer outcomes are retained as exact observations
and may become pre-generation questions for a similar future job; the system
never treats progression as proof of why the employer selected the application.

Save the portal's questionnaire/answer summary before submitting whenever the
portal permits it. Joblooper copies and hash-binds that private evidence because
knockout answers are especially important when a decision arrives quickly. If
answers were not captured, record that absence; do not recreate them from
memory. `--confirm-external` is a narrow retrospective recovery option: the
user must identify the exact sent files, each must still match the approved
manifest, and any changed unsent file remains disclosed.

## Safety expectations

- Keep runtime data and application documents private.
- Never publish a personal repository or reuse its Git history publicly.
- Review every CV and letter; evidence integrity does not guarantee hiring.
- Treat match confidence as evidence coverage, not an ATS score or interview
  probability.
- If an exact JD, submission or response correlation cannot be established,
  Joblooper stops instead of assuming.
