# Engineering and security review

Reviewed on 29 October 2026 by the backend/QA reviewer against the separately implemented offline neural adapter, worker protocol, downloader and frontend API integration. This record is scoped evidence, not a zero-bug or universal-device guarantee.

## Executed checks

From the application folder, `python -m unittest discover -s tests -v` passed **50 tests** on Windows/Python 3.12. The run completed in 1.168 seconds. Local HTTP networking was enabled for the integration tests. No neural model was loaded, speech provider contacted or model asset downloaded by this test suite.

- 33 core/HTTP tests: validation boundaries, boolean/NaN rejection, Unicode and control characters, deterministic chunking, literal pronunciation replacement, voice defaults/presets, fixed-text voice preview, shared generation lock, stale/missing audio rejection, PCM WAV parsing, silence/DC rejection, safe ZIP paths, HTML escaping, export content, host/origin protection, request limits and failure responses.
- 12 isolated adapter tests: missing-model and busy states, exact Unicode/voice forwarding, unique request IDs, rejection of stale/cross-request output, malformed responses, EOF, invalid base64/WAV, timeout termination, cleanup, restart with a new response queue, `shell=False`, and explicit offline/telemetry environment flags. Subprocesses and responses were mocked.
- 5 isolated installer tests: pinned revision, POSIX/Windows traversal and alternate-stream path rejection, SHA-256 verification for LFS assets, Git blob SHA-1 verification for regular files, same-size corrupt cache replacement, valid cache reuse and failure without asset replacement. HTTPS responses were mocked.

## Findings resolved during review

| Finding | Resolution verified |
| --- | --- |
| Persistent worker responses lacked request identity, risking wrong audio being associated with a later request. | UUID request ID is sent, echoed and checked exactly; stale output stops the worker. Regression test passes. |
| Worker EOF, error/scalar responses and cleanup failures could leave unusable state. | Malformed/error responses stop the process; cleanup resets global process/queue state before guarded termination. Restart tests pass. |
| Nonzero constant PCM and unsigned silence could pass a simple byte check. | Only mono PCM16 at 22,050/24,000 Hz is accepted; complete frames, duration, size and nontrivial peak-to-peak variation are checked. |
| Existing audio did not depend on voice selection. | Signatures include language, pace, voice and spoken text; changed settings reject stale audio. Older text drafts import with the default voice, but old audio must be regenerated. |
| Windows drive-relative/alternate-stream paths and same-size corrupt regular model assets were insufficiently checked. | Installer rejects drive/root/backslash/colon paths, checks resolved containment, and verifies cached/new regular-file Git blob hashes as well as LFS SHA-256. |
| Health UI could imply that inference had already succeeded. | Wording distinguishes installed neural files from a successful generation; first generation still loads the model. |
| Rejected large HTTP requests could reset the connection on Windows before a useful error arrived. | Small rejected bodies are drained under a fixed limit; the HTTP regression receives 413. |

## Boundary and remaining limits

No known critical/high issue remained in the reviewed local backend/worker boundary at this revision. The application is a single-user loopback service, not an authenticated public or multi-tenant deployment. Do not expose its port to a network.

The one-time installer intentionally uses the network to obtain pinned model files. Inference code uses local model paths, `local_files_only=True`, `trust_remote_code=False`, disabled optional ASR loading and offline environment flags; no cloud, browser speech or system speech fallback was found in the reviewed implementation. This static/protocol review is not a packet-capture claim or a review of every transitive ML dependency.

Health availability checks installed files/runtime presence. It does not certify that the model loads, that a requested voice sounds as described, or that Urdu pronunciation is correct. Real English/Urdu audio generation, listening, timing/resource measurements and browser/device workflow verification are separate release evidence owned by the delivery run. CPU generation can take minutes and has a bounded timeout; short chapters and teacher listening review remain necessary.

WAV validation and text/settings signatures verify format, output variation and cache consistency. They are not speech recognition and cannot prove that the model said every word correctly. The exported ZIP deliberately includes an answer key and answers in its manifest; review/remove those before learner distribution where answers must be withheld.

The review does not establish every-device compatibility, measured WCAG conformance, a broad multilingual quality score, successful hosted CI, GitHub upload or LinkedIn publication. Those claims require their own recorded evidence.
