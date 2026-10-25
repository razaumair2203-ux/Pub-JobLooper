# Security and privacy

Repository behavior is declared in `repo-policy.json`. In a
`PERSONAL_PRIVATE` source, governed candidate truth, application packages and
evidence under `.joblooper/` may be committed intentionally; its remote and
every clone must remain private. A `PUBLIC_SKILL` mirror must contain no
candidate runtime data and must start with new Git history.

Do not enable a push URL until the hosting repository’s private visibility and
access list have been checked while authenticated. Never publish this repository
or turn its existing history into the public edition.

## Local dashboard boundary

The dashboard listens only on IPv4 loopback. Every request is rejected unless
its `Host` is the active `127.0.0.1` or `localhost` port, which prevents a
rebinding hostname from using the browser as a route into local records.

`/api/session` establishes a host-only, HttpOnly, `SameSite=Strict` session
cookie. All private JSON reads and artifact downloads require that cookie.
State-changing requests additionally require the matching random token in a
custom header and an exact loopback `Origin`. Static assets expose no personal
data, use a strict self-only content policy, and revalidate with content ETags.

These controls protect the browser boundary; they do not make an unlocked local
machine safe from another process running as the same operating-system user.

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
