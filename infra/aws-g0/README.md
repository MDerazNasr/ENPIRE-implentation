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

## Deployment sequence

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

The user's Identity Center principal now has explicitly approved temporary
`AdministratorAccess` assignments in both member accounts. Local profiles
`enpire-audit` and `enpire-evaluator` resolve to the correct account IDs, and
AWS CloudFormation `validate-template` accepts both templates. The receipt is
`results/agent-supervisor/g0/aws-temporary-bootstrap-access-v1.json`. This is
bootstrap access only and does not satisfy the independent-reviewer boundary.
It must be narrowed after infrastructure verification and before production
custody can be accepted.

Audit change set `g0-audit-initial-v1` was first created for review only and
reached `CREATE_COMPLETE/AVAILABLE`. Its pre-execution review receipt is
`results/agent-supervisor/g0/aws-audit-change-set-review-v1.json`. After exact
approval, execution failed while creating `AnchorWriterRole`: IAM rejected the
trust policy because it named the not-yet-created evaluator role as a
principal. CloudFormation rolled the stack back to `ROLLBACK_COMPLETE`.

The two empty compliance-locked buckets were retained as designed:

- `enpire-g0-audit-anchorbucket-a6fzfrpcdmc7`
- `enpire-g0-audit-auditlogbucket-13fyadzqjtn7`

Both had Object Lock enabled with 30-day compliance retention, versioning,
AES256 default encryption, and all public-access blocks. Both were empty when
inspected. Their stack-created bucket policies were rolled back, and the roles
and policies were deleted. The terminal receipt is
`results/agent-supervisor/g0/aws-audit-stack-attempt-1-terminal.json`.

The template now uses the evaluator account root as the syntactically valid
trust principal and constrains `aws:PrincipalArn` to the exact future evaluator
role. This preserves the intended caller boundary while allowing the audit
stack to be created before the evaluator role exists.

After a second exact approval, both named empty retained buckets and the failed
stack metadata were deleted and their absence verified. No stored data was
deleted. Cleanup receipt:
`results/agent-supervisor/g0/aws-audit-stack-attempt-1-cleanup.json`.

Corrected change set `g0-audit-corrected-v2` reached
`CREATE_COMPLETE/AVAILABLE` for review and is preserved in
`results/agent-supervisor/g0/aws-audit-change-set-review-v2.json`. It was never
executed and has now been deleted as superseded.

A dedicated Identity Center user and `ENPIREG0VerifierAccess` permission set
now exist. The permission set has no managed-policy attachments and grants only
`sts:AssumeRole` on `enpire-g0-independent-verifier` in the audit account. Its
bootstrap receipt is
`results/agent-supervisor/g0/aws-independent-verifier-bootstrap-v1.json`.
Technical identity separation exists. An initial user attestation was retained
in `results/agent-supervisor/g0/aws-independent-verifier-portal-confirmation-v1.json`,
but subsequent menu details showed three accounts with `AdministratorAccess`.
That was the existing administrator session, not the dedicated verifier. The
correction is preserved in
`results/agent-supervisor/g0/aws-independent-verifier-portal-correction-v2.json`.
Dedicated-verifier login and account visibility therefore remain unconfirmed.
The expected verifier view is only the audit account with
`ENPIREG0VerifierAccess`. The target verifier role cannot be assumed until the
stack creates it. The user subsequently completed the administrator-issued
password setup and reported the exact expected portal view: one `enpire-audit`
account and only `ENPIREG0VerifierAccess`. This successful corrected
attestation is preserved in
`results/agent-supervisor/g0/aws-independent-verifier-portal-confirmation-v3.json`.
Independent human ownership/control remains unverified and is not accepted.

Replacement change set `g0-audit-independent-verifier-v3` is
preserved at its pre-execution `CREATE_COMPLETE/AVAILABLE` state in the review receipt:
`results/agent-supervisor/g0/aws-audit-change-set-review-v3.json`. It has not
been altered since review.

After exact approval and a caller-identity gate, v3 executed once and the audit
stack reached `CREATE_COMPLETE`. Terminal receipt:
`results/agent-supervisor/g0/aws-audit-stack-attempt-2-terminal.json`. All six
resources reached `CREATE_COMPLETE`. The new empty buckets are
`enpire-g0-audit-anchorbucket-qqxtjqex5jbf` and
`enpire-g0-audit-auditlogbucket-pewvp64nueuy`; both enforce 30-day COMPLIANCE
Object Lock, versioning, AES256, complete public-access blocking, non-public
policies, and TLS-only access. The anchor writer is put-only to `anchors/*` and
trusts only the exact future evaluator role. The verifier role is read-only and
trusts only the dedicated Identity Center verifier role. Neither IAM role has
managed-policy attachments.

The dedicated verifier subsequently authenticated as the exact
`AWSReservedSSO_ENPIREG0VerifierAccess` principal and successfully assumed
`enpire-g0-independent-verifier`. Through that role, reads confirmed versioning
and 30-day COMPLIANCE Object Lock on both buckets. Independent version
enumeration failed closed because the deployed policy grants `s3:ListBucket`
but not `s3:ListBucketVersions`. The complete partial result is preserved in
`results/agent-supervisor/g0/aws-independent-verifier-role-validation-v1.json`.
Do not claim full independent evidence verification until that missing action
is reviewed, explicitly approved, deployed, and retested.

The local audit template now adds only `s3:ListBucketVersions` to that role's
bucket-read actions. Five focused tests, the offline security checker, and
CloudFormation lint pass. With explicit review-only approval, update change set
`g0-audit-verifier-list-versions-v4` was created in the audit account. It is
preserved at its pre-execution `CREATE_COMPLETE/AVAILABLE` state and contains
exactly one in-place modification to `IndependentVerifierRole`. Review receipt:
`results/agent-supervisor/g0/aws-audit-change-set-review-v4.json`.

After separate exact execution approval and repeat identity/diff/hash gates,
v4 executed once and the stack reached `UPDATE_COMPLETE`. The live verifier
role now includes `s3:ListBucketVersions` and still has no managed policies.
The dedicated verifier then successfully assumed the role and independently
confirmed both empty version inventories, versioning, non-public policies, and
30-day COMPLIANCE Object Lock. Execution receipt:
`results/agent-supervisor/g0/aws-audit-verifier-policy-update-terminal-v1.json`;
successful retest:
`results/agent-supervisor/g0/aws-independent-verifier-role-validation-v2.json`.

No private object was uploaded, no evaluator stack was deployed, and no GPU,
scientific evaluation, candidate decision, or promotion occurred. Independent
human control remains unverified, so this successful technical read boundary
is not production custody acceptance.

## Evaluator-account readiness inventory

A read-only inventory of evaluator account `960946312280` found no active
CloudFormation stacks and no ENPIRE IAM roles. Its only Identity Center account
assignment is the temporary administrator; the directory has no confirmed
independent evaluator/custodian human or independently controlled verifier
human. The template's direct trust principals must exist before stack creation.
Its `ReceiptVerifierRole` also needs review for the same
`s3:ListBucketVersions` permission required by the audit verifier.

The inventory is preserved in
`results/agent-supervisor/g0/aws-evaluator-readiness-inventory-v1.json`. Do not
create an evaluator change set until the missing humans and concrete
least-privilege principals are supplied and separately approved. Do not reuse
the temporary same-operator verifier identity as proof of independent human
custody.

## Interim evaluator technical identities

On 2026-09-17, under the explicitly accepted single-operator protected mode,
three one-hour Identity Center permission sets were created for the existing
administrator: coordinator, custodian, and evaluator operator. Each can only
call `sts:AssumeRole` on its exact future evaluator-account application role.
The existing verifier permission set was extended only to the future evaluator
receipt-verifier role and assigned to the existing temporary verifier user in
the evaluator account. All four assignments completed, their generated
AWS-reserved roles have no attached managed policies, and the evaluator account
still has no stack, bucket, or `enpire-g0-*` application role.

The exact receipt is
`results/agent-supervisor/g0/aws-evaluator-technical-identity-bootstrap-v1.json`.
This establishes technical identities, not independent human custody. The old
verifier permission-set description still refers only to the audit role; its
read-back inline policy is authoritative and contains exactly the two approved
verifier roles. No evaluator change set or deployment is authorized by this
bootstrap.

## Evaluator change-set review

With separate review-only approval, change set
`g0-evaluator-single-operator-review-v1` was created in evaluator account
`960946312280`. It is `CREATE_COMPLETE/AVAILABLE` and remains unexecuted. The
diff contains exactly eleven additions: three S3 buckets, four IAM roles, three
bucket policies, and one CloudTrail. The placeholder stack
`enpire-g0-evaluator` remains `REVIEW_IN_PROGRESS` with zero resources and no
outputs. Post-review checks found zero buckets, zero `enpire-g0-*` application
roles, and zero trails in the evaluator account.

The full review receipt is
`results/agent-supervisor/g0/aws-evaluator-change-set-review-v1.json`. Executing
this change set would activate irreversible 30-day COMPLIANCE Object Lock on
three buckets and create the remaining roles and trail. Review approval does
not authorize execution; a separate exact execution approval is mandatory.
