# AWS G0 custody infrastructure

These CloudFormation templates prepare the independent storage and evaluator
boundary described by the G0 production-acceptance runbook. They do not deploy
compute, upload final resets or model weights, execute an evaluator, activate a
campaign, or authorize paid/GPU work.

## Account boundary

Use two different AWS account IDs:

- **Evaluator account:** final inputs, worker evidence, evaluator ledger, and
  the evaluator/worker/custodian roles.
- **Audit account:** immutable ledger-head anchors and the cross-account
  CloudTrail archive.

The independent verifier principal should be controlled outside the candidate,
training-worker, and evaluator automation chain. Do not satisfy this by giving
one unrestricted local credential access to every role.

## What the templates create

`audit-account.template.json` creates:

- an S3 Object Lock compliance-mode anchor bucket;
- an S3 Object Lock compliance-mode CloudTrail archive bucket;
- a put-only anchor-writer role trusted by the evaluator role; and
- an audit/anchor read-only verifier role.

`evaluator-account.template.json` creates:

- separate final-input, worker-evidence, and evaluator-ledger buckets;
- Object Lock compliance retention, versioning, encryption, public-access
  blocking, and retain-on-stack-change controls on all three;
- a put-only worker role that cannot read final inputs or delete evidence;
- separate custody-provisioner, evaluator, and receipt-verifier roles; and
- a multi-region CloudTrail with log validation and S3 data events delivered
  to the audit account.

Five buckets are retention-locked. The default and minimum retention period is
30 days. Compliance-mode Object Lock is intentionally difficult to reverse;
deployment therefore requires a separate exact human approval.

## Offline validation

No AWS credentials or network call are needed:

```bash
python3 scripts/check_g0_aws_infrastructure.py
```

The checker verifies the template hashes, locked-bucket controls, absence of
delete permissions, worker exclusion from final inputs, verifier exclusion
from final object reads, and the cross-account trail parameter.

## Deployment sequence — not yet authorized

1. Create the evaluator and audit accounts, enable MFA, and configure AWS IAM
   Identity Center/SSO profiles. Never place access keys in the repository or
   chat.
2. Confirm both account identities with `aws sts get-caller-identity` and
   capture only account IDs and principal ARNs in a non-authorizing preflight.
3. Deploy the audit stack first and record its output bucket/role identities.
4. Deploy the evaluator stack using those exact audit outputs.
5. Independently inspect versioning, Object Lock, public-access blocks, role
   policies, CloudTrail status, and account separation.
6. Only after that verification, separately authorize transfer of the private
   final-reset artifact to the custody-provisioner role.
7. Generate the public custody/deployment receipts without recording private
   object paths, ordered reset IDs, credentials, or signed URLs.

Do not deploy either stack merely to test syntax. After SSO is configured, use
CloudFormation validation and change sets first. Review the change set and the
final cost/retention envelope before executing it.

## Current account provisioning status

Account-creation attempt 1 is retained in
`results/agent-supervisor/g0/aws-account-creation-attempt-1.json`. The audit
account was created successfully. The evaluator request failed because AWS
reported that the requested email already belongs to an AWS account. No retry
was inferred. After exact approval, attempt 2 used a different unique alias and
created the evaluator account successfully; its receipt is
`results/agent-supervisor/g0/aws-account-creation-attempt-2.json`. Both member
accounts now exist. No stack, bucket, lock, or private upload has occurred.
