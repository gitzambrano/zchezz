# Syzygy Tablebases

Both supported engine families contain a Syzygy bridge. Native tablebase probing depends on local Fathom source/header availability and tablebase files; these resources are intentionally not required for a clean checkout build.

## Build behavior

The shared Makefile enables Fathom only when the expected source/header pair is available for the selected engine. Otherwise it defines `NO_TABLEBASES`.

```bash
make -C engine/build ENGINE=v325 native
make -C engine/build ENGINE=v500 native
```

Both commands must remain buildable without local tablebases.

## UCI options

The engine exposes Syzygy path/probe controls. An empty path disables probing. Probe depth/limit settings are applied by the UCI layer to the search globals used by the selected engine.

## Testing policy

Normal 200 ms strength comparisons keep tablebases off so results are portable and do not depend on local TB cache/storage. Tests specifically targeting tablebases may enable them and must record the available piece count/path.

A build that compiled with `NO_TABLEBASES` is not evidence that probing works; it only proves the no-tablebase configuration builds.
