# Joblooper user guide

Joblooper turns one user-approved career record and one captured job
description into a traceable CV and cover-letter package. It does not search
old CVs while drafting and does not create employer-facing files before you
approve the complete text in chat.

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
python jl.py preflight <exact-job-key>
python jl.py plan <exact-job-key>
python jl.py present <exact-job-key>
```

Answer only the material questions returned by `preflight`. `present` shows the
entire CV, cover letter, omission disclosure and rejection-risk assessment in
chat. No DOCX or PDF exists yet.

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

## 5. Record submission and responses

Record the exact submitted files so a later response can be correlated without
guessing:

```text
python jl.py submit <exact-job-key> --sent-file "<path-to-CV>" --cover-letter-file "<path-to-letter>" --channel portal
python jl.py response rejection-email.txt
python jl.py case <exact-job-key>
```

Rejection explanations remain hypotheses. Joblooper requires competing causes,
counterevidence, unknowns and multiple substantive reasoning passes before a
lesson can be retained. Only an employer-stated reason may be marked confirmed.
Interview, progression and offer outcomes are retained as exact observations
and may become pre-generation questions for a similar future job; the system
never treats progression as proof of why the employer selected the application.

## Safety expectations

- Keep runtime data and application documents private.
- Never publish a personal repository or reuse its Git history publicly.
- Review every CV and letter; evidence integrity does not guarantee hiring.
- Treat match confidence as evidence coverage, not an ATS score or interview
  probability.
- If an exact JD, submission or response correlation cannot be established,
  Joblooper stops instead of assuming.
