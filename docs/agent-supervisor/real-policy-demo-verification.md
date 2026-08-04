# Real Policy Demo Verification

Date: 2026-08-04

Status: implementation, repository regression verification, visual QA, and
clean-commit rehearsal complete.

## Acceptance coverage

- deterministic reward-only residual-policy training;
- fixed shared reset set and three paired seeds;
- one allowlisted recorded config proposal;
- real isolated Git candidate and unchanged stable HEAD;
- six bounded CPU subprocess workers with observed overlap;
- strict evidence normalization through `TrialEvidence`;
- independent frozen D1 `KEEP` decision;
- JSON/CSV/Markdown/HTML/SVG evidence;
- 14-file SHA-256 manifest and tamper rejection;
- machine-local path disclosure scan;
- explicit toy/RLT/live-provider claim boundary; and
- dirty-repository rejection before output.

## Development rehearsal

- control mean success: 11.85%;
- candidate mean success: 100.00%;
- paired mean improvement: 88.15 percentage points;
- evaluator decision: `KEEP`;
- maximum observed concurrent workers: 6;
- external calls and GPU/LLM cost: zero; and
- focused tests: 6 passed.
- complete repository coverage: 200 tests passed in four bounded groups
  (49 D1/Phase-1, 41 M4–M9, 104 supervisor-core, and 6 real-demo tests).

These numbers are real for the deterministic public toy task and have no RLT or
robotics interpretation.

## Final clean-commit rehearsal

- implementation commit: `28fc951`;
- result fingerprint:
  `9ae476d209b1f69c368cf084e01ce283df49961e377e0b5c7373ee711ec6ce15`;
- curated artifacts: 14, independently rehashed successfully;
- supervisor HEAD/worktree after execution: unchanged and clean; and
- output: `/tmp/enpire-real-policy-demo-28fc951`.

## Visual QA

Quick Look rendered the page successfully at 1400 pixels. The warning banner,
headline, result cards, `KEEP` decision, and before/after trajectory visual are
legible and ordered correctly. The in-app browser automation connection was
not available; interactive browser behavior is therefore not claimed.
