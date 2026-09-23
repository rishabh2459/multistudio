# multicam-engine

Pure-Python processing engine. **Never imports web/UI code.** Usable from the
CLI (`multicam`), the FastAPI backend, and future cloud workers.

| Module        | Purpose                                       | Phase |
|---------------|-----------------------------------------------|-------|
| `models`      | Core data model + exact time math             | 0     |
| `benchmark`   | Ground truth for real-footage accuracy tests  | 0     |
| `media`       | Probe, normalize, audio extraction, proxies   | 1     |
| `sync`        | GCC-PHAT offset, drift, confidence            | 1     |
| `analysis`    | VAD, energy, noise floor, mic bleed           | 2     |
| `decide`      | Switch logic, presets, hysteresis             | 2     |
| `render`      | ffmpeg filter graph, encoders, audio mix      | 3     |
| `export`      | FCPXML / Premiere XML / EDL / SRT / VTT       | 7, 9  |
| `reframe`     | Face detection, smoothing, crop planning      | 8     |
| `transcribe`  | faster-whisper, word timings, fillers         | 9, 10 |
