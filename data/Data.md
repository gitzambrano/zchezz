# Zchezz training data

The dataset conventions, the manifest format and the catalog live in
[`docs/datasets.md`](../docs/datasets.md). Each dataset directory here carries a
tracked `manifest.json` with its measured contents and provenance.

```bash
python train/labeling/manifest.py              # read-only status
python train/labeling/manifest.py --generate   # refresh manifests after data changes
python train/labeling/manifest.py --catalog    # refresh the catalog in docs/datasets.md
```
