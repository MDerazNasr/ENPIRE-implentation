# Experiment config

`phase1_overrides.yaml` contains exactly the four documented fields this
checkpoint permits at its config boundary. Runtime paths come from environment
variables; full resolved commands and configurations live with each run under
`results/`.

`d1/` contains JSON-compatible YAML profiles for the gated scientific
baseline. Keeping them in the JSON subset lets the no-GPU validator and
dry-run launcher remain dependency-free. Profiles are external Hydra override
sets; they do not copy or edit RLinf configuration internals.
