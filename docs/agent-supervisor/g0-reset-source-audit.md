# G0 Reset Generator Source Audit

Status: **source-derived repeat and live CPU reset confirmation passed; final
artifact custody and full scientific runtime identity remain pending**

This audit used public source and a local CPU-only simulator reset check. It did
not load a model, step an environment, evaluate a policy, use a GPU, or contact
a paid service.

## Pinned installation

- RLinf: `/private/tmp/enpire-g0-runtime/RLinf`, clean detached commit
  `c90951a0c799a750cb5294ed10587c61cc2af8bf`.
- ManiSkill: `/private/tmp/enpire-g0-runtime/ManiSkill`, clean tag
  `v3.0.0b22`, commit `33967b9e3ead1f841eec57cc9f31d0d8b8cf0907`.
- Isolated Python: `/private/tmp/enpire-g0-runtime/reset-venv`, Python 3.12.13
  with NumPy 1.26.4. This environment contains no model weights.

The full RLinf/OpenPI/Torch environment was intentionally not installed: only
3.9 GiB was initially free, and model/training dependencies are unnecessary to
derive the pinned reset seed sequence.

## Important semantic finding

RLinf creates an internal `reset_state_ids` tensor by drawing 256 values with
replacement from `0..126`. Those values are passed as `options["episode_id"]`,
but ManiSkill `BaseEnv.reset` does not interpret that option for this tabletop
task. They are therefore not the initial evaluation-state identities.

On the initial fixed evaluation reset, RLinf passes scalar seed 2026 (or 2027)
to ManiSkill. Pinned ManiSkill expands that scalar into 256 episode seeds as:

```text
[seed] + numpy.random.RandomState(seed).randint(2**31, size=255)
```

Those episode seeds drive task randomization and are the authoritative reset
identities. The capture implementation binds the complete RLinf environment,
config, task variant, ManiSkill base environment, and ManiSkill task source
hashes. It refuses dirty or wrong commits and requires NumPy 1.26.4.

## Results

Two independent captures were byte-identical:

- capture semantic SHA-256:
  `17736b3c22e31d91b9984c3449af76bd648adaec4f56e68ba79a7a655db6460a`;
- capture file SHA-256:
  `5a5486c19fbcb9637df028c9e2c364f0c3a2d1f4d4d9de57342b042cbc7318f8`;
- development artifact SHA-256:
  `e5466ff22121cf1429a1f710639cc31ed14b67430e3c84f3760fd184a3a6e161`;
- final artifact SHA-256:
  `27165db099dfaddc66a6eced98156110acb2e877289eb1c503ae53a446d2fa97`;
- each set contains 256 unique episode seeds; intersection is zero; and
- repeat receipt SHA-256:
  `455d5d744a99a91c6bc17217fe8c3390b6d968de0b38eb813e7e3699cd1b94ce`.

The development artifact and public hash receipts are under
`results/agent-supervisor/g0/reset-sets/`. The ordered final IDs are deliberately
not stored in the repository or any candidate context. Their hash is public;
acceptance still requires placement under separately controlled evaluator
custody and a public custody record that does not disclose the IDs.

## Claim boundary and next check

This is real reset-path engineering evidence, not synthetic fixture data. A
cached Linux x86_64 container was used because exact SAPIEN 3.0.1 has no macOS
ARM64 wheel. The installed check stack was NumPy 1.26.4, Torch 2.8.0+cpu,
SAPIEN 3.0.1, Gymnasium 0.29.1, and the pinned ManiSkill source. Mesa llvmpipe
was installed only to diagnose rendering; the accepted check disabled rendering.

`scripts/run_g0_reset_runtime_confirmation.py` instantiated the exact task as
a one-environment CPU worker and performed all 512 resets sequentially. This is
semantically equivalent to the accepted multiprocess adapter, which expands
the scalar seed then sends each worker one explicit seed. Both observed ordered
arrays matched, uniqueness was 256/256, overlap was zero, and no final IDs were
printed. Runtime receipt SHA-256:
`76beecb21038536c432010c40987a70758cea5dddd2ddc57fcdf01cb6950c4da`.

Retain two failed setup attempts as engineering evidence: the read-only editable
install tried to create `.eggs`, and the first task reset lacked a usable Vulkan
device. Neither reached a reset. A SciPy 1.8/NumPy compatibility warning was
present during the passing reset check; SciPy is not used by the seed-expansion
or task-reset path, but the full scientific runtime must use its separately
frozen dependency set.
