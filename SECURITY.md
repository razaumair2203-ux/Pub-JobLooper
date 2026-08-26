# Security and privacy

Repository behavior is declared in `repo-policy.json`. In a
`PERSONAL_PRIVATE` source, governed candidate truth, application packages and
evidence under `.joblooper/` may be committed intentionally; its remote and
every clone must remain private. A `PUBLIC_SKILL` mirror must contain no
candidate runtime data and must start with new Git history.

Do not enable a push URL until the hosting repository’s private visibility and
access list have been checked while authenticated. Never publish this repository
or turn its existing history into the public edition.

## Public release boundary

Create a public edition only with:

```powershell
python tools/export_public.py D:\new\empty\joblooper-public
```

The exporter uses an allowlist, excludes `.joblooper` and binary evidence,
rewrites policy to `PUBLIC_SKILL`, checks known direct identifiers, and audits
the proposed tree. Inspect it manually, run all checks, then initialize a new
Git repository there. The new history is the security boundary.

If private data ever enters the public mirror, removing the current file is
insufficient. Take the mirror offline, revoke exposed credentials where
relevant, rewrite affected public refs with a suitable history-cleaning tool,
audit again, and replace old clones. Do not rewrite the private personal source
merely because it legitimately contains personal data.

## Integrity limits

Release manifests use SHA-256 to detect change after build. A digest proves
integrity, not truth or authenticity. Candidate sign-off and source review are
still required. Secret-pattern and identifier scans are last-line controls;
they cannot prove that prose contains no indirect personal detail.

Report concerns privately to the repository owner. Do not include candidate
documents or identifiers in a public issue.
