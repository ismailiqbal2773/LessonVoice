# LessonVoice — classroom learning packs

Owner approval: 27 October 2026, this chat. Build, test, validate before GitHub upload. Include a workflow flowchart, responsive UI/UX, and evidence of checks. Independent engineering/security review before release.

## Scope

### Final owner correction and delivery boundary — 29 October 2026

Strictly offline **neural** speech is required: OmniVoice from an exact local snapshot, no eSpeak/Windows/cloud fallback. The validated CPU environment is Python 3.12 in `.neural-venv`, with pinned requirements. Four instruction/seed voice characters are offered; neither consistent personal identity nor perfect pronunciation is promised. Pace is relative to baseline 150, not exact WPM. First-run model installation downloads approximately 3.3 GB; inference remains local. App source and model/tokenizer licenses are distinct; this configuration carries the upstream model's CC-BY-NC designation and Boson/Meta tokenizer conditions, documented prominently before installation. Do not advertise unrestricted commercial model use.
Teacher-provided English or Urdu lesson text becomes editable sections. Teacher enters pronunciation replacements and comprehension question/answer pairs. Generate real downloadable local speech for each section, listen, then export a reusable ZIP containing audio, original transcript, spoken-text transcript, questions and metadata. No automatic question generation, PDF understanding, cloned voice or external AI provider in this release.

Application host: Python 3.12+ on a desktop/laptop, loopback-only local HTTP. Mobile/tablet browser layout is responsive; do not imply a phone hosts the Python service or that localhost can be accessed from another device. English/Urdu voice feasibility is a release gate. No paid service or credentials. Avoid copying VoiceStudio code: cite it as research inspiration and observe each actual dependency's license.

## Acceptance criteria
1. Create, sample-load, edit and restore one draft; clear explicitly. Invalid imports do not partially replace it.
2. Split supplied text into bounded editable sections, with stable IDs. Empty/oversized inputs have clear errors.
3. Preview original and spoken text; pronunciation rules apply literally and deterministically. Empty replacements, duplicate rules and invalid language rejected.
4. Generate actual WAV audio using an available local engine. Show working/progress/error states. Engine/language unavailability is clear; no fake successful audio.
5. Edits to spoken text/language/voice settings invalidate stale audio and block export until regenerated; title-only edits do not invalidate speech.
6. Teacher-authored questions and answers export correctly, preserving Unicode. Answer-key visibility is deliberate in the exported pack.
7. Download a validated ZIP; verify audio duration/header and matching manifest/transcripts. Export has no absolute paths or private environment data.
8. Workflow diagram explains draft -> segment -> edit -> pronounce -> generate -> listen -> export, with accessible step controls and reduced-motion handling.
9. UI works with keyboard, narrow and wide viewport layouts, touch-sized controls, visible focus and labelled fields. Verify real browser rendering where tools permit.
10. Server validates content type, host/origin, sizes and routes, executes no lesson text as commands, uses no document logging and never exposes general filesystem access.

## Release gates
Unit/integration tests, actual English/Urdu audio smoke tests, exported pack inspection, desktop and mobile/tablet browser checks, security/dependency review and second-engineer review. No known critical/high bugs. Record untested platforms and speech-quality limitations. Zero-bug / all-device guarantees are not claims this project can substantiate.
