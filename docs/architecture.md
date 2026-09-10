# Architecture

Zchezz is a C11 UCI chess engine with two supported engine profiles.

- `v325` is the default profile and uses NNU3.
- `v500` is a supported secondary profile and uses NNU4 HalfKP-4-Bucket.

Generic orchestration is version-independent and resolves profiles through `utils/engine_profiles.py`. Network-specific encoders, models, importers, exporters, and C evaluators remain separate because their binary contracts differ.

Cross-family games use UCI process boundaries. Native in-process arena/selfplay tools use `v500` as their NNU4 host and are not the cross-family abstraction.

`engine/ACTIVE_ENGINE` selects the default user-facing engine and remains `v325` until an explicit promotion.
