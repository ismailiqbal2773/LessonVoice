# Architecture and mechanism

LessonVoice is a trusted single-user loopback application: a Python standard-library HTTP server, vanilla browser UI and a persistent local OmniVoice inference worker. It is not a hosted multi-user service or native mobile app. The responsive interface can fit phone-sized viewports; the configured runtime runs on the local PC.

## Runtime and installation

Python 3.12 uses the isolated `.neural-venv` environment and `requirements-lock.txt`: OmniVoice 0.2.1, CPU PyTorch/torchaudio 2.8.0 and Transformers 5.21.0. `tools/download_model.py` installs approximately 3.3 GB once, validating upstream file sizes and available hashes. Model revision: `c5fdb5ccb189668d56333f77ba2629f4cd7535f4`. Weights are downloaded separately and are not redistributed in this repository. See the noncommercial model and tokenizer terms in THIRD_PARTY_NOTICES.md before use.

The server supervises a persistent worker loading local files on CPU in float32. Offline library flags and socket connection denial prevent inference from downloading models or contacting a remote speech service. Installation itself needs network access. There is no cloud or synthetic-engine fallback.

## Data flow

Teacher text → bounded sections → literal simultaneous pronunciation replacements → exact spoken-text preview → local neural WAV → browser playback → validated ZIP. Longest literal matches win; replacements do not cascade. Original and spoken transcripts remain distinct. Teacher-authored questions and a separate answer key are exported with an explicit sharing warning.

The browser stores an editable draft in localStorage and audio/object URLs only in tab memory. Structural draft validation permits unfinished editing states; strict server validation applies to speech and export. Missing voice fields in older drafts default to `warm-female`. Other malformed imports preserve the existing draft.

Four instruction/seed presets select voice character, not guaranteed stable personal identities. Pace is a relative multiplier (`rate / 150`), not an exact words-per-minute promise. Urdu and pronunciation require teacher listening review.

Each audio signature is SHA-256 of UTF-8 compact JSON `[language,rate,voice,spokenText]`. Speech-setting or actual spoken-text changes invalidate the cache. In-flight revision guards discard stale responses. Export recomputes signatures and checks WAV structure, size and duration before building the ZIP in memory.

## Failure and security boundaries

Generation is serialized with bounded requests and a worker timeout. Missing files, load failures and inference errors produce actionable errors while preserving text; no fake audio is returned. UI controls lock relevant actions while work is pending. First model load and CPU generation can be slow.

Host/Origin checks protect the loopback API. Fixed routes prevent arbitrary file reads. Browser text uses textContent; exported HTML is escaped. Filenames are app-generated and lesson text never becomes shell command text. Request, section, WAV and ZIP bounds limit accidental resource exhaustion. These controls do not make this a hardened public service; keep the loopback binding.

## Evidence and operations

Health reports file/runtime availability, not successful inference or pronunciation quality. A recorded eight-sample English/Urdu CPU probe produced 2.49–4.07 seconds of audio in 18.65–35.34 seconds per sample. Its socket-denial probe recorded zero attempted connections. These are observations for those short samples on the tested machine, not throughput or universal privacy guarantees.

Restarting preserves browser text but requires audio regeneration. Export draft JSON before upgrades. Restore the source, matching lockfile and local model revision to roll back; do not rely on a different environment's unpinned packages. Other operating systems, GPUs and all-device compatibility have not been established by these measurements.
