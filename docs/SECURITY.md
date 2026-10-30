# Security status and supported use

Reviewed 29 October 2026. This is a **local, trusted-user, noncommercial demonstration**, with known dependency advisories. It has not passed a clean dependency scan and is not approved as a public or multi-user service.

## Release decision

Source publication as a clearly labelled local demonstration is acceptable within the boundary below. This review did not establish a remotely reachable critical/high vulnerability through the current LessonVoice HTTP API. That is a scoped reachability assessment, not proof that the neural dependency stack is safe. Deployment on the internet, shared hosting, a LAN listener, or use with untrusted model files is blocked pending dependency remediation and a fresh review.

The application's 50 automated tests and separately recorded real speech/UI checks establish specific behavior; they do not eliminate dependency vulnerabilities, guarantee every device, or constitute penetration testing. Resource exhaustion remains possible for another process/user on the same computer: neural inference is expensive, requests are bounded rather than authenticated, and the worker timeout is long.

## Boundary examined

The server binds to `127.0.0.1`. It checks exact localhost Host/Origin combinations, restricts routes and JSON sizes, validates text/settings and PCM WAV exports, escapes exported HTML, and uses fixed ZIP entry names. Host/Origin checks reduce browser cross-origin attacks; they are not authentication against local programs.

The speech worker receives validated text, a language, a bounded rate, and one of four fixed presets. It loads a fixed local model directory, with `local_files_only=True`, `trust_remote_code=False`, and ASR disabled. The installed model and audio tokenizer use safetensors. No API accepts model paths, checkpoints, Python objects, TorchScript programs, image files, reference recordings, or voice-clone prompt files. JSON/base64 PCM exports do not enter Pillow or `torch.load`.

The installer deliberately uses HTTPS once to obtain a pinned revision. It checks resolved path containment and asset size plus LFS SHA-256 or Git blob SHA-1 before replacement. Preserve the downloaded model/runtime as trusted local files: a local attacker able to modify them is outside this application's protection. Offline environment variables and Python socket guards prevent the worker's normal network paths; they are not an operating-system firewall or a security sandbox for native code.

## Dependency advisories retained

`artifacts/dependency-audit.json` is the initial 92-package OSV snapshot, before partial remediation. Its advisory IDs include aliases and must not be presented as a count of unique vulnerabilities. `requirements-lock.txt` records the final selected versions; the initial snapshot is not a final clean scan.

| Package | Selected version | Assessment and remaining work |
| --- | --- | --- |
| filelock | 4.2.4 | Upgraded from the initially flagged 3.32.3. Recheck the final environment rather than claiming the initial findings all remain or all disappeared. |
| setuptools | 81.0.0 | Partial remediation from 78.1.0. Later legacy-build advisories still require newer releases. Runtime HTTP requests do not invoke package installation, PackageIndex, or project builds. Do not build/install untrusted source distributions in this environment. |
| Pillow | 12.3.0 | Image parser advisories remain reported. The installed upstream Gradio dependency constrains Pillow below 13; upgrading across that constraint needs compatibility work. LessonVoice does not start the Gradio demo, provide image routes, or parse images, so no corresponding HTTP input path was found. Presence of this package is still residual risk. |
| torch / torchaudio | 2.8.0+cpu | Torch advisories remain reported, including memory-corruption operations and model/deserialization paths. Newer official CPU wheels tested by the release owner failed Windows DLL initialization on this host; the working version was restored. This compatibility problem does not waive the advisories. Upgrade the supported host runtime and framework together, then rerun inference, application tests, and the dependency audit. |

The initial Torch records include `GHSA-qfhq-4f3w-5fph`, `GHSA-rrmf-rvhw-rf47`, `GHSA-vgrw-7cvw-pwgx`, `PYSEC-2025-203`, `PYSEC-2025-204`, `PYSEC-2025-206`, `PYSEC-2026-139`, and `PYSEC-2026-2286`. The [OSV lstm_cell record](https://osv.dev/vulnerability/GHSA-qfhq-4f3w-5fph) and [unpack_sequence record](https://osv.dev/vulnerability/GHSA-vgrw-7cvw-pwgx) describe local memory-corruption cases. Severity text and scoring differ within these records; do not call all findings harmless or all critical on that basis.

Inspection found no explicit LSTM/unpack_sequence/JIT calls in the application's worker or the installed OmniVoice inference model. OmniVoice does contain `torch.load` in optional voice-clone prompt loading and evaluation, and pickle/JIT operations in auxiliary denoising scripts. LessonVoice does not call those features. The inference path still executes native PyTorch operations; this review did not instrument every transitive operator, reproduce every advisory, or prove all findings unreachable. Fixed trusted models and the absence of arbitrary tensor/model input substantially narrow the exposed paths, but cannot provide a blanket exemption.

## Operating and release constraints

- Keep the loopback binding and same-origin restrictions; do not put a tunnel or reverse proxy in front of this server.
- Use a dedicated local environment and the pinned installer/model. Do not add arbitrary checkpoints, pickle/voice-prompt imports, Gradio endpoints, image ingestion, or user-controlled model paths without renewed review.
- Keep sensitive lessons off shared computers. Drafts can persist in browser local storage; downloaded ZIPs contain lesson text and the explicitly included teacher answer key.
- The configured pretrained model has noncommercial licensing restrictions; consult `THIRD_PARTY_NOTICES.md`. Source availability does not grant commercial model rights.
- Before expanding beyond this demonstration: resolve the remaining advisories on a compatible supported runtime, produce a fresh full dependency report, review actual advisory prerequisites against the inference graph, and add authentication/resource isolation appropriate to that deployment.

If a vulnerability is found, stop running the affected copy and report the affected version, route/operation, and a minimal reproduction to the repository maintainer without posting private lesson content or executable malicious artifacts in public issues.


## 30 October 2026 speech update

Offline remains the default. Local OmniVoice now uses 64 synthesis steps. Audio/voice-preview requests may include a separate `speech` object: `{provider:"elevenlabs", apiKey:"...", voiceId:"...", consent:true}`. This explicitly sends spoken text to the fixed ElevenLabs HTTPS endpoint using eleven_v3 and pcm_24000. Credentials are request-scoped, excluded from project/draft/export metadata and never logged. Missing/invalid settings are rejected; no automatic cloud fallback exists. Previous offline review statements apply to offline mode only. Paid synthesis still requires account credits and live validation with a funded key. See README.
