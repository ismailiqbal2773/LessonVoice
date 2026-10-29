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
