# NNUE Engineering Notes

The repository supports two NNUE formats.

- `v325`: NNU3, `799 -> 256 -> 64 -> 1`, 426864-byte installed weight file.
- `v500`: NNU4 HalfKP-4-Bucket, `2560 -> 48`, perspective concat `96`, `20 -> 1`, 248020-byte installed weight file.

Training data remains architecture-neutral until encoding. Each trainer/exporter must reject incompatible checkpoint architecture metadata. `checkpoints/<profile>/latest.pt` is the canonical resumable checkpoint. Installed engine weights plus the profile importer must be sufficient to reconstruct a resumable checkpoint when no PyTorch checkpoint exists.

Use `python tools/check_nnue.py` for the default v325 artifact or `python tools/check_nnue.py --profile v500` for v500.
