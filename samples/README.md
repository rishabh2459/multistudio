# Test footage

Everything in this folder except this README is git-ignored (files are large).
Keep a backup of this folder somewhere safe (external drive / cloud drive of your choice).

Layout — one folder per recording:

```
samples/
  T1/
    cam1.mp4
    cam2.mp4
    meta.json          # written by hand
    labels.txt         # exported from Audacity
    ground_truth.json  # generated: make gt-build REC=samples/T1
    _audio/            # generated WAVs for labeling
```

Full protocol: `docs/TEST_FOOTAGE.md`.
