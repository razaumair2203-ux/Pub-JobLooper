# Bounded employer-context review

Use this optional review after deterministic planning and before chat
presentation. Its purpose is to find a material, truthful improvement—not to
produce generic recruiter advice or pretend to predict rejection.

## Research threshold

Research only when the exact advert leaves a material selection question that
official employer evidence could clarify. Prefer the exact advert, then no more
than four current official sources: a closely comparable role, location/careers
policy, joining/security policy and one relevant employee profile. Do not use
anecdotal trend pages as fact.

Record `.joblooper/work/<key>/EMPLOYER-CONTEXT.json` using schema
`joblooper.employer-context.v1`:

- bind it to the exact captured JD URL and research date;
- keep one to five sources, each with URL and concise observed fact;
- label each finding `OBSERVED` or `INFERRED` and `HIGH`, `MEDIUM` or `LOW`;
- cite candidate anchor IDs only when the finding is CV-addressable;
- choose `REPLAN` only when an existing verified anchor can correct an error or
  materially improve visible fit;
- otherwise choose `LEAVE_AS_IS` and explain the remaining external or
  employer-specific risk.

Never convert employer context, online hiring patterns, role similarity or a
plausible hypothesis into candidate experience. Confidence is support for the
factor—not a numerical probability of interview or rejection.
