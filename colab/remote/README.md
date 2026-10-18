# Remote runtime entry points

This directory contains implementations that execute inside a Colab VM.
The CLI and browser transports can invoke the same remote workload.
`../layout.json` lists compatibility entry points retained for existing notebooks.
Use the canonical paths in new scripts. Preserve the compatibility entry points
until their external callers migrate.

These programs can build engines, generate datasets, train models, or terminate
an identified launcher. Use their help or inspection mode before a real launch.
Persist checkpoints and completed shards outside the ephemeral VM filesystem.
