"""Deterministic core and local HTTP regressions; no model or paid service."""
import base64
from copy import deepcopy
from http.server import ThreadingHTTPServer
from io import BytesIO
import json
from pathlib import Path
import struct
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler
import wave
import zipfile

from lessonvoice import core, server


def project():
    return {"version": 1, "title": "Plants", "language": "en", "rate": 150, "voice": "warm-female",
            "sections": [{"id": "intro", "title": "Introduction", "text": "Plants need water and sunlight."}],
            "pronunciations": [], "questions": [{"question": "What do plants need?", "answer": "Water and sunlight."}]}


def wav_data(seconds=.1, width=2, constant=None, sample_rate=22050):
    stream = BytesIO()
    with wave.open(stream, "wb") as writer:
        writer.setnchannels(1); writer.setsampwidth(width); writer.setframerate(sample_rate)
        samples = [constant if constant is not None else (500 if i % 2 else -500) for i in range(int(sample_rate * seconds))]
        writer.writeframes(bytes(samples) if width == 1 else struct.pack(f"<{len(samples)}h", *samples))
    return stream.getvalue()


def entries(p):
    return [{"id": s["id"], "data": base64.b64encode(wav_data()).decode("ascii"),
             "signature": core.audio_signature(p["language"], p["rate"], p.get("voice", "warm-female"), s["text"])} for s in core.spoken_sections(p)]


class ProjectTests(unittest.TestCase):
    def test_cloud_export_provenance_excludes_credentials(self):
        p = project()
        data = core.export_pack(p, entries(p), {'provider':'elevenlabs','voiceId':'publicVoice','apiKey':'private-secret'})
        with zipfile.ZipFile(BytesIO(data)) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            self.assertEqual(manifest['speechSource']['model'], 'eleven_v3')
            self.assertEqual(manifest['speechSource']['voiceId'], 'publicVoice')
            for name in archive.namelist():
                self.assertNotIn(b'private-secret', archive.read(name))
        with self.assertRaises(ValueError):
            core.export_pack(p, entries(p), {'provider':'unknown'})

    def test_canonical_validation_no_mutation_or_private_fields(self):
        p = project(); p["title"] = "  Plants\r\nlesson  "; p["private"] = "C:/private"
        before = deepcopy(p); clean = core.validate_project(p)
        self.assertEqual(clean["title"], "Plants\nlesson")
        self.assertNotIn("private", clean); self.assertEqual(p, before)

    def test_required_bounds_and_types(self):
        invalid = [("version", True), ("version", 2), ("title", ""), ("title", "x" * 121),
                   ("language", "fr"), ("rate", True), ("rate", 99), ("rate", 221), ("rate", 150.5),
                   ("rate", float("nan")), ("voice", ""), ("voice", "external-provider"), ("voice", None),
                   ("voice", False), ("sections", []), ("pronunciations", {}), ("questions", None)]
        for field, value in invalid:
            with self.subTest(field=field, value=str(value)[:12]):
                p = project(); p[field] = value
                with self.assertRaises(ValueError): core.validate_project(p)

    def test_section_ids_and_content_limits(self):
        for value in ["../file", "", "x" * 65, 3]:
            p = project(); p["sections"][0]["id"] = value
            with self.subTest(value=value), self.assertRaises(ValueError): core.validate_project(p)
        p = project(); p["sections"] *= 2
        with self.assertRaisesRegex(ValueError, "unique"): core.validate_project(p)
        p = project(); p["sections"][0]["text"] = "x" * 1501
        with self.assertRaises(ValueError): core.validate_project(p)

    def test_four_voice_presets_and_backward_compatible_drafts(self):
        for voice in core.VOICE_IDS:
            p = project(); p["voice"] = voice
            self.assertEqual(core.validate_project(p)["voice"], voice)
        p = project(); del p["voice"]
        self.assertEqual(core.validate_project(p)["voice"], "warm-female")
        p = project(); p["sections"] = [{"id": str(i), "title": "Part", "text": "x" * 1000} for i in range(21)]
        with self.assertRaisesRegex(ValueError, "20,000"): core.validate_project(p)
        p = project(); p["sections"] = [{"id": str(i), "title": "Part", "text": "x"} for i in range(25)]
        with self.assertRaises(ValueError): core.validate_project(p)

    def test_controls_and_surrogates(self):
        for value in ["secret\x00text", "secret\ud800text", "secret\x1btext"]:
            p = project(); p["sections"][0]["text"] = value
            with self.assertRaises(ValueError): core.validate_project(p)

    def test_spoken_phoneme_commands_rejected_after_replacement(self):
        p = project(); p["sections"][0]["text"] = "[[p l a n t]]"
        with self.assertRaisesRegex(ValueError, "plain lesson text"): core.validate_project(p)
        p = project(); p["pronunciations"] = [{"term": "Plants", "say": "[[x]]"}]
        with self.assertRaisesRegex(ValueError, "plain lesson text"): core.validate_project(p)
        p = project(); p["title"] = "[[title]]"
        self.assertEqual(core.validate_project(p)["title"], "[[title]]")

    def test_pronunciation_literal_longest_simultaneous(self):
        rules = [{"term": "A+B", "say": "sum"}, {"term": "A", "say": "B"}, {"term": "B", "say": "C"}]
        self.assertEqual(core.spoken_text("A+B, A and B; a+b", rules), "sum, B and C; a+b")
        self.assertEqual(core.spoken_text("تعلیم اور کتاب", [{"term": "کتاب", "say": "کِتاب"}]), "تعلیم اور کِتاب")

    def test_bad_pronunciation_rules_and_expansion(self):
        for rules in [[{"term": "x", "say": ""}], [{"term": "x", "say": "a"}, {"term": "x", "say": "b"}],
                      [{"term": "x\ny", "say": "x"}], [{"term": "x", "say": "z" * 121}]]:
            p = project(); p["pronunciations"] = rules
            with self.assertRaises(ValueError): core.validate_project(p)
        p = project(); p["sections"][0]["text"] = "a" * 100
        p["pronunciations"] = [{"term": "a", "say": "b" * 120}]
        with self.assertRaisesRegex(ValueError, "too long"): core.validate_project(p)

    def test_question_validation(self):
        for questions in [[{"question": "Q?", "answer": ""}], [{"question": "", "answer": "A"}],
                          [{"question": "Q" * 501, "answer": "A"}], ["not a question"]]:
            p = project(); p["questions"] = questions
            with self.assertRaises(ValueError): core.validate_project(p)
        p = project(); p["questions"] = []
        self.assertEqual(core.validate_project(p)["questions"], [])


class SegmentTests(unittest.TestCase):
    def test_unicode_chunks_stable_ids_and_no_lost_content(self):
        text = "First paragraph.\n\n" + "تعلیم کے لیے کتاب ضروری ہے۔ " * 100
        sections = core.segment(text)
        self.assertGreater(len(sections), 2)
        self.assertTrue(all(0 < len(s["text"]) <= 1500 for s in sections))
        self.assertEqual(sections, core.segment(text))
        self.assertEqual(len(set(s["id"] for s in sections)), len(sections))
        self.assertEqual("".join(s["text"] for s in sections).replace(" ", ""), text.replace("\n", "").replace(" ", ""))

    def test_unbroken_word(self):
        self.assertEqual([len(s["text"]) for s in core.segment("a" * 4000)], [1500, 1500, 1000])

    def test_empty_large_and_many_paragraphs(self):
        for value in ["", " \n ", None, "a" * 20001, "\n\n".join(["short"] * 25)]:
            with self.assertRaises(ValueError): core.segment(value)


class ExportTests(unittest.TestCase):
    def test_signature_javascript_contract(self):
        import hashlib
        self.assertEqual(core.audio_signature("ur", 150, "warm-female", "کتاب"), hashlib.sha256('["ur",150,"warm-female","کتاب"]'.encode()).hexdigest())

    def test_pack_audio_unicode_manifest_and_no_private_path(self):
        p = project(); p["language"] = "ur"; p["title"] = "تعلیم"; p["sections"][0]["text"] = "کتاب ضروری ہے۔"; p["private"] = "C:/secret"
        with zipfile.ZipFile(BytesIO(core.export_pack(p, entries(p)))) as archive:
            self.assertEqual(set(archive.namelist()), {"index.html", "manifest.json", "original-transcript.txt", "spoken-transcript.txt", "questions.txt", "answer-key.txt", "audio/section-01.wav"})
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(manifest["title"], "تعلیم")
            self.assertEqual(manifest["voice"], "warm-female")
            self.assertGreater(manifest["sections"][0]["durationSeconds"], 0)
            self.assertNotIn("C:/secret", archive.read("manifest.json").decode())
            self.assertIn("کتاب ضروری ہے۔", archive.read("original-transcript.txt").decode())
            self.assertEqual(core.validate_wav(archive.read("audio/section-01.wav"))["sampleRate"], 22050)

    def test_html_escape_and_safe_filenames(self):
        p = project(); p["title"] = '<script>alert("title")</script>'; p["sections"][0]["text"] = '<img src=x onerror="alert(1)">'
        p["sections"][0]["title"] = "../../script.html"; p["questions"][0]["question"] = "<script>Q</script>"
        with zipfile.ZipFile(BytesIO(core.export_pack(p, entries(p)))) as archive:
            page = archive.read("index.html").decode()
            self.assertNotIn("<script>", page); self.assertNotIn("<img", page); self.assertIn("&lt;script&gt;", page)
            self.assertTrue(all(".." not in name for name in archive.namelist()))
            self.assertIn("Content-Security-Policy", page)

    def test_missing_duplicate_unknown_stale_audio(self):
        p = project()
        for audio in [[], entries(p) * 2, [{**entries(p)[0], "id": "unknown"}], [{**entries(p)[0], "signature": "old"}]]:
            with self.assertRaises(ValueError): core.export_pack(p, audio)
        audio = entries(p)
        for field, value in [("language", "ur"), ("rate", 160), ("voice", "clear-male")]:
            changed = deepcopy(p); changed[field] = value
            with self.assertRaisesRegex(ValueError, "out of date"): core.export_pack(changed, audio)
        p["sections"][0]["text"] += " New content."
        with self.assertRaisesRegex(ValueError, "out of date"): core.export_pack(p, audio)

    def test_title_only_changes_keep_audio_valid(self):
        p = project(); audio = entries(p); p["title"] = "Updated"; p["sections"][0]["title"] = "New section"
        self.assertTrue(core.export_pack(p, audio).startswith(b"PK"))

    def test_legacy_audio_signature_rejected_but_legacy_draft_imports(self):
        import hashlib
        p = project(); del p["voice"]
        legacy = entries(p)
        legacy[0]["signature"] = hashlib.sha256('["en",150,"Plants need water and sunlight."]'.encode()).hexdigest()
        with self.assertRaisesRegex(ValueError, "out of date"): core.export_pack(p, legacy)
        self.assertTrue(core.export_pack(p, entries(p)).startswith(b"PK"))

    def test_pronunciation_invalidates_audio(self):
        p = project(); audio = entries(p); p["pronunciations"] = [{"term": "Plants", "say": "Plant life"}]
        with self.assertRaisesRegex(ValueError, "out of date"): core.export_pack(p, audio)

    def test_bad_base64_and_truncated_wav(self):
        p = project()
        for data in ["%%%", base64.b64encode(b"not a wave").decode(), base64.b64encode(wav_data()[:-50]).decode()]:
            with self.assertRaises(ValueError): core.export_pack(p, [{**entries(p)[0], "data": data}])

    def test_wav_real_header_duration_and_silence(self):
        self.assertGreater(core.validate_wav(wav_data())["durationSeconds"], 0)
        self.assertEqual(core.validate_wav(wav_data(sample_rate=24000))["sampleRate"], 24000)
        quiet = wav_data()
        quiet = quiet[:44] + b"\x01\x00\x02\x00" * ((len(quiet) - 44) // 4) + (b"\x01\x00" if (len(quiet) - 44) % 4 else b"")
        for data in [b"", b"RIFF" + b"0" * 40, wav_data(.01), wav_data(constant=0), wav_data(width=1, constant=128), wav_data(constant=200), quiet, wav_data(sample_rate=44100)]:
            with self.subTest(size=len(data)), self.assertRaises(ValueError): core.validate_wav(data)

    def test_export_audio_size_limit(self):
        p = project()
        with patch.object(core, "MAX_AUDIO_BYTES", 50):
            with self.assertRaises(ValueError): core.export_pack(p, entries(p))
        with patch.object(core, "MAX_PACK_AUDIO", 50):
            with self.assertRaisesRegex(ValueError, "pack limit"): core.export_pack(p, entries(p))


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.worker = threading.Thread(target=cls.http.serve_forever, daemon=True); cls.worker.start()
        cls.base = f"http://127.0.0.1:{cls.http.server_port}"; cls.opener = build_opener(ProxyHandler({}))

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown(); cls.http.server_close(); cls.worker.join()

    def request(self, path, data=None, headers=None, raw=None, method=None):
        body = raw if raw is not None else (json.dumps(data, ensure_ascii=False).encode() if data is not None else None)
        return self.opener.open(Request(self.base + path, data=body, headers=headers or {"Content-Type": "application/json"}, method=method), timeout=10)

    def test_health_and_security_headers(self):
        with patch.object(server, "engine_status", return_value={"name": "fixture", "available": True, "languages": ["en", "ur"]}):
            with self.request("/api/health") as response:
                self.assertTrue(json.load(response)["engine"]["available"])
                self.assertEqual(response.headers["Cache-Control"], "no-store"); self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")

    def test_segment_spoken_audio_export_journey(self):
        with self.request("/api/segment", {"text": "Hello.\n\nWorld."}) as response: self.assertEqual(len(json.load(response)["sections"]), 2)
        p = project(); p["pronunciations"] = [{"term": "Plants", "say": "Plant life"}]
        with self.request("/api/spoken", {"project": p}) as response: spoken = json.load(response)["sections"][0]["text"]
        self.assertTrue(spoken.startswith("Plant life"))
        with patch.object(server, "engine_status", return_value={"available": True, "languages": ["en"]}), patch.object(server, "synthesise", return_value=wav_data()) as engine:
            with self.request("/api/audio", {"project": p, "sectionId": "intro"}) as response:
                audio = response.read(); self.assertEqual(response.headers["Content-Type"], "audio/wav")
            engine.assert_called_once_with(spoken, "en", 150, "warm-female")
        audio = [{"id": "intro", "data": base64.b64encode(audio).decode(), "signature": core.audio_signature("en", 150, "warm-female", spoken)}]
        with self.request("/api/export", {"project": p, "audio": audio}) as response:
            self.assertIn("lessonvoice-pack.zip", response.headers["Content-Disposition"])
            self.assertEqual(response.headers["Content-Type"], "application/zip")
            with zipfile.ZipFile(BytesIO(response.read())) as archive: self.assertIn("audio/section-01.wav", archive.namelist())

    def test_unavailable_timeout_runtime_and_no_internal_leak(self):
        with patch.object(server, "engine_status", return_value={"available": False, "languages": [], "message": "Install voice engine."}):
            with self.assertRaises(HTTPError) as error: self.request("/api/audio", {"project": project(), "sectionId": "intro"})
            self.assertEqual(error.exception.code, 503)
        for failure in [RuntimeError("private path"), TimeoutError("private path")]:
            with patch.object(server, "engine_status", return_value={"available": True, "languages": ["en"]}), patch.object(server, "synthesise", side_effect=failure):
                with self.assertRaises(HTTPError) as error: self.request("/api/audio", {"project": project(), "sectionId": "intro"})
                self.assertEqual(error.exception.code, 503); self.assertNotIn("private path", error.exception.read().decode())
        with patch.object(server, "engine_status", side_effect=RuntimeError("secret")):
            with self.assertRaises(HTTPError) as error: self.request("/api/health")
            self.assertEqual(error.exception.code, 503); self.assertNotIn("secret", error.exception.read().decode())

    def test_voice_preview_uses_fixed_language_sample_and_settings(self):
        for language in ("en", "ur"):
            with patch.object(server, "engine_status", return_value={"available": True, "languages": ["en", "ur"]}), patch.object(server, "synthesise", return_value=wav_data(sample_rate=24000)) as engine:
                with self.request("/api/voice-preview", {"language": language, "rate": 170, "voice": "calm-male", "text": "Must not be spoken"}) as response:
                    self.assertEqual(response.headers["Content-Type"], "audio/wav")
                    self.assertEqual(core.validate_wav(response.read())["sampleRate"], 24000)
                args = engine.call_args.args
                self.assertNotEqual(args[0], "Must not be spoken")
                self.assertIn("LessonVoice" if language == "en" else "لیسن وائس", args[0])
                self.assertEqual(args[1:], (language, 170, "calm-male"))
        with patch.object(server, "engine_status", return_value={"available": True, "languages": ["en"]}), patch.object(server, "synthesise", return_value=wav_data()) as engine:
            with self.request("/api/voice-preview", {"language": "en", "rate": 150}) as response:
                self.assertEqual(response.status, 200)
            self.assertEqual(engine.call_args.args[3], "warm-female")

    def test_voice_preview_validates_before_engine_call(self):
        with patch.object(server, "synthesise") as engine:
            for values in [{"language": "fr", "rate": 150}, {"language": "en", "rate": True}, {"language": "ur", "rate": 150, "voice": "remote"}]:
                with self.assertRaises(HTTPError) as error: self.request("/api/voice-preview", values)
                self.assertEqual(error.exception.code, 400)
            engine.assert_not_called()
        with patch.object(server, "engine_status", return_value={"available": True, "languages": ["en"]}):
            with self.assertRaises(HTTPError) as error: self.request("/api/voice-preview", {"language": "ur", "rate": 150})
            self.assertEqual(error.exception.code, 503)

    def test_voice_preview_uses_shared_lock_and_sanitized_engine_errors(self):
        settings = {"language": "en", "rate": 150, "voice": "storyteller-female"}
        server._synthesis_lock.acquire()
        try:
            with patch.object(server, "engine_status", return_value={"available": True, "languages": ["en"]}):
                with self.assertRaises(HTTPError) as error: self.request("/api/voice-preview", settings)
                self.assertEqual(error.exception.code, 503)
        finally: server._synthesis_lock.release()
        with patch.object(server, "engine_status", return_value={"available": True, "languages": ["en"]}), patch.object(server, "synthesise", side_effect=RuntimeError("secret model path")):
            with self.assertRaises(HTTPError) as error: self.request("/api/voice-preview", settings)
            self.assertEqual(error.exception.code, 503)
            self.assertNotIn("secret model path", error.exception.read().decode())

    def test_audio_concurrency_lock(self):
        server._synthesis_lock.acquire()
        try:
            with patch.object(server, "engine_status", return_value={"available": True, "languages": ["en"]}):
                with self.assertRaises(HTTPError) as error: self.request("/api/audio", {"project": project(), "sectionId": "intro"})
                self.assertEqual(error.exception.code, 503)
        finally: server._synthesis_lock.release()

    def test_bad_host_origin_and_routes(self):
        for headers in [{"Content-Type": "application/json", "Origin": "https://evil.example"}, {"Content-Type": "application/json", "Host": "evil.example"}, {"Content-Type": "application/json", "Origin": "null"}]:
            with self.assertRaises(HTTPError) as error: self.request("/api/segment", {"text": "Hello"}, headers)
            self.assertEqual(error.exception.code, 403)
        for path in ["/../docs/PRD.md", "/api/private", "/index.html?path=secret"]:
            with self.assertRaises(HTTPError) as error: self.request(path)
            self.assertEqual(error.exception.code, 404)

    def test_json_media_types_limits_and_invalid_section(self):
        for raw in [b"not json", b"[]", b'{"text":NaN}', b'{"text":Infinity}', b"\xff"]:
            with self.subTest(raw=raw), self.assertRaises(HTTPError) as error: self.request("/api/segment", raw=raw)
            self.assertEqual(error.exception.code, 400)
        with self.assertRaises(HTTPError) as error: self.request("/api/segment", {"text": "hi"}, {"Content-Type": "text/plain"})
        self.assertEqual(error.exception.code, 415)
        with self.assertRaises(HTTPError) as error: self.request("/api/segment", {"text": "a" * 300001})
        self.assertEqual(error.exception.code, 413)
        with self.assertRaises(HTTPError) as error: self.request("/api/audio", {"project": project(), "sectionId": "missing"})
        self.assertEqual(error.exception.code, 400)

    def test_unsupported_methods_are_safe(self):
        for method in ["PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"]:
            with self.subTest(method=method), self.assertRaises(HTTPError) as error: self.request("/api/health", method=method)
            self.assertEqual(error.exception.code, 405)

    def test_static_whitelist_missing_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / "web").mkdir(); (root / "web/index.html").write_text("<h1>LessonVoice</h1>")
            with patch.object(server, "ROOT", root):
                with self.request("/") as response: self.assertIn(b"LessonVoice", response.read())
                with self.assertRaises(HTTPError) as error: self.request("/style.css")
                self.assertEqual(error.exception.code, 503)


if __name__ == "__main__": unittest.main()
