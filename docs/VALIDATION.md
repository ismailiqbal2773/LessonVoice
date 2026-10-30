# Validation — 29 October 2026

Engineering, QA and independent security review were executed on Windows/Python3.12.

- 50 automated tests pass:33 core/API,12 isolated worker protocol,5 pinned-model installer tests.
- JavaScript syntax check passed. Dependency installation is consistent via pip check; OSV scan is NOT clean, see SECURITY.md for scope, residual risks and release restrictions.
- Eight real neural samples: English and native-script Urdu across all four instruction/seed presets; 24000Hz monoPCM16. Initial CPU generation18.65–35.34s for2.49–4.07s output. Outbound socket-denial probe recorded zero attempts. These are synthesis/integrity measurements, not listener pronunciation ratings.
- Final adapter after filelock/setuptools updates and enforced worker socket blocking: English warm-female122924bytes/2.56s (84.52s cold+contention); Urdu clear-male184364bytes/3.84s (35.52s). Both passed WAV validation through actual bounded subprocess protocol.
- Chrome real UI: notes→editable chapter; teacher question/answer; actual English generation; native audio readyState4 and advancing playback; ZIP download then ZIP CRC/integrity and expected entries/voice metadata verified. Urdu fixed voice preview decoded at4.09s/readyState4. Voice changes removed old audio and disabled export. Reload preserved unfinished fields; JSON draft download/import restored the exact editable lesson. Keyboard arrow navigation selected question tab. Animated mechanism changed steps.
- Responsive Chrome viewport checks:390px phone,768px tablet and1280/1440px desktop; no document horizontal overflow at390/768. Genuine tablet workflow recording and desktop playback inspected. This is viewport simulation, not physical iOS/Safari/Android certification. The local server is a computer-hosted loopback tool, not a native mobile application.
- Independent findings and fixes:REVIEW.md; upstream advisories/restricted-release assessment:SECURITY.md. No guarantee of zero bugs or perfect pronunciation.
- Video:32s square HyperFrames film with real browser capture, offline neural narration, summaries and actual voice samples. Render evidence lives in the delivery workspace. Video does not claim live generation speed.

## Reproduce

`python -m unittest discover -s tests -v`

`node --check web/app.js`

Install using README, launch server, generate English/Urdu samples, play before exporting. Keep offline weights separate from source; no real pupil data used in demos.


## 30 October 2026 update

- 55 automated tests pass (50 existing + 4 cloud adapter tests + 1 export privacy test). JavaScript syntax check passes. Cloud tests mock the provider; they are not live paid synthesis.
- Actual Chrome UI produced a 5.32s English warm-female WAV and a 2.28s Urdu clear-male WAV with the 64-step worker. Native audio decoded at readyState 4. Urdu Play changed to pause, then playback reached its end. Both ZIP exports were downloaded and inspected: CRC clean, expected player/transcripts/questions/answer key/manifest and mono 24kHz PCM audio present.
- Paid settings expose provider, password field, voice ID and explicit consent. Provider change removes prior audio and disables ZIP export. A second simultaneous generation received a busy error. Funded paid synthesis has NOT been tested; no real API key was supplied.
- One browser download-event wait timed out and reset the automation session; the actual exported ZIP was found and validated on disk. This was not a synthesis failure.
- [English sample](samples/quality64-en.wav) / [Urdu sample](samples/quality64-ur.wav) are actual browser-generated 64-step output. English text: “Water changes into vapour when the sun warms it. This process is called evaporation.” Urdu text: “پودوں کو پانی اور روشنی چاہیے۔” No listener score, intelligibility benchmark or claim of human-indistinguishable speech is established. Raising steps is a quality-oriented configuration change, not a measured naturalness win against other models.
- Previous independent security review predates paid mode. Known upstream advisories and local noncommercial demo restrictions still apply.

- Additional current browser checks: teacher question/answer entry, Urdu pronunciation replacement (“پانی” → “صاف پانی”) in spoken-text preview, missing paid API key error, draft restoration on reload and reset to local provider with empty key. Phone-width measurement (390px) showed no horizontal overflow. Tablet screenshot capture was interrupted; previous tablet evidence is dated above, not recertified here.

- Final current server HTTP smoke: exported actual generated English WAV with `speechSource` metadata, CRC clean; paid preview without credentials returns 400. Final video: 32s, 1080×1080 H264/AAC; complete 5.32s English and 2.28s Urdu samples placed without cuts; HyperFrames check passes. Decoded paid-settings frame inspected.
