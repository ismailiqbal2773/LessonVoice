"""Offline worker protocol regressions. No neural model is loaded by these tests."""
import base64
from io import BytesIO
import json
import queue
import struct
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch
import wave
from pathlib import Path

from lessonvoice import tts


def audio_fixture():
    output = BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(24000)
        wav.writeframes(struct.pack("<2400h", *[1000 if i % 2 else -1000 for i in range(2400)]))
    return output.getvalue()


class FakeInput:
    def __init__(self):
        self.requests = []

    def write(self, value):
        self.requests.append(json.loads(value))

    def flush(self):
        pass


class FakeProcess:
    def __init__(self):
        self.stdin = FakeInput()
        self.stdout = BytesIO()
        self.killed = False
        self.waited = False

    def poll(self):
        return 0 if self.killed else None

    def kill(self):
        self.killed = True

    def wait(self, timeout):
        self.waited = True
        return 0


class Responses:
    def __init__(self, process, response=None):
        self.process = process
        self.response = response
        self.timeouts = []

    def get(self, timeout):
        self.timeouts.append(timeout)
        if self.response:
            return self.response(self.process.stdin.requests)
        return json.dumps({"requestId": self.process.stdin.requests[-1]["requestId"],
                           "audio": base64.b64encode(audio_fixture()).decode()}).encode()


class TtsValidationTests(unittest.TestCase):
    def test_invalid_inputs_rejected_before_status_or_process(self):
        bad = [("", "en", 150, "warm-female"), ("x" * 3001, "en", 150, "warm-female"),
               (False, "en", 150, "warm-female"), ("hello", "fr", 150, "warm-female"),
               ("hello", "en", True, "warm-female"), ("hello", "en", float("nan"), "warm-female"),
               ("hello", "en", 99, "warm-female"), ("hello", "en", 221, "warm-female"),
               ("hello", "en", 150, "remote")]
        with patch.object(tts, "engine_status") as status, patch.object(tts, "_start") as start:
            for settings in bad:
                with self.subTest(settings=str(settings)[:40]), self.assertRaises(ValueError): tts.synthesise(*settings)
            status.assert_not_called(); start.assert_not_called()

    def test_missing_model_has_no_fallback_or_process(self):
        with patch.object(tts, "engine_status", return_value={"available": False}), patch.object(tts, "_start") as start:
            with self.assertRaisesRegex(RuntimeError, "setup is incomplete"): tts.synthesise("hello", "en", 150)
            start.assert_not_called()

    def test_busy_does_not_start_worker(self):
        tts._lock.acquire()
        try:
            with patch.object(tts, "engine_status", return_value={"available": True}), patch.object(tts, "_start") as start:
                with self.assertRaisesRegex(RuntimeError, "busy"): tts.synthesise("hello", "en", 150)
                start.assert_not_called()
        finally:
            tts._lock.release()

    def test_installed_status_is_capability_not_quality_probe(self):
        assets = ('config.json', 'model.safetensors', 'tokenizer.json', 'tokenizer_config.json',
                  'audio_tokenizer/config.json', 'audio_tokenizer/model.safetensors',
                  'audio_tokenizer/preprocessor_config.json', 'REVISION')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(tts, "MODEL", root), patch.object(tts, "_python", return_value="isolated-runtime"):
                self.assertFalse(tts.engine_status()["available"])
                for name in assets:
                    target = root / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(b"fixture")
                status = tts.engine_status()
                self.assertTrue(status["available"])
                self.assertIn("first generation loads", status["message"])
                self.assertEqual(status["languages"], ["en", "ur"])


class WorkerProtocolTests(unittest.TestCase):
    def call(self, process, responses, text="Plants need sunlight.", language="en", voice="warm-female"):
        with patch.object(tts, "_process", process), patch.object(tts, "_responses", responses), \
             patch.object(tts, "engine_status", return_value={"available": True}), patch.object(tts, "_start"):
            return tts.synthesise(text, language, 150, voice)

    def test_success_preserves_unicode_and_voice_and_unique_request_id(self):
        process = FakeProcess(); responses = Responses(process)
        with patch.object(tts, "_process", process), patch.object(tts, "_responses", responses), \
             patch.object(tts, "engine_status", return_value={"available": True}), patch.object(tts, "_start"):
            first = tts.synthesise("کتاب ضروری ہے۔", "ur", 170, "calm-male")
            second = tts.synthesise("Plants need water.", "en", 130, "clear-male")
        self.assertEqual(first, audio_fixture()); self.assertEqual(second, audio_fixture())
        self.assertEqual(process.stdin.requests[0]["text"], "کتاب ضروری ہے۔")
        self.assertEqual(process.stdin.requests[0]["voice"], "calm-male")
        self.assertEqual(process.stdin.requests[1]["rate"], 130)
        self.assertNotEqual(process.stdin.requests[0]["requestId"], process.stdin.requests[1]["requestId"])
        self.assertTrue(all(len(request["requestId"]) == 32 for request in process.stdin.requests))
        self.assertFalse(process.killed); self.assertEqual(responses.timeouts, [840, 840])

    def test_late_or_cross_request_audio_is_not_accepted(self):
        process = FakeProcess()
        def stale(requests):
            return json.dumps({"requestId": "0" * 32, "audio": base64.b64encode(audio_fixture()).decode()}).encode()
        with self.assertRaisesRegex(RuntimeError, "worker failed"): self.call(process, Responses(process, stale))
        self.assertTrue(process.killed); self.assertTrue(process.waited)
        self.assertFalse(tts._lock.locked())
        # A clean next worker can serve a new request after a protocol failure.
        replacement = FakeProcess()
        self.assertEqual(self.call(replacement, Responses(replacement)), audio_fixture())

    def test_timeout_kills_worker_and_releases_lock(self):
        process = FakeProcess()
        def timeout(_): raise queue.Empty()
        with self.assertRaisesRegex(RuntimeError, "14 minutes"): self.call(process, Responses(process, timeout))
        self.assertTrue(process.killed); self.assertFalse(tts._lock.locked())

    def test_worker_errors_eof_and_malformed_responses_are_stopped(self):
        response_factories = [lambda _: None, lambda _: b"not JSON", lambda _: b"[]", lambda _: b"42",
                              lambda requests: json.dumps({"requestId": requests[-1]["requestId"], "error": "private engine path"}).encode(),
                              lambda requests: json.dumps({"requestId": requests[-1]["requestId"]}).encode(),
                              lambda requests: json.dumps({"requestId": requests[-1]["requestId"], "audio": "%%%"}).encode(),
                              lambda requests: json.dumps({"requestId": requests[-1]["requestId"], "audio": base64.b64encode(b"invalid wav").decode()}).encode()]
        for factory in response_factories:
            process = FakeProcess()
            with self.subTest(factory=factory), self.assertRaises(RuntimeError) as error:
                self.call(process, Responses(process, factory))
            self.assertNotIn("private engine path", str(error.exception)); self.assertTrue(process.killed)
            self.assertFalse(tts._lock.locked())

    def test_broken_stdin_stops_and_releases_lock(self):
        process = FakeProcess(); process.stdin.flush = MagicMock(side_effect=BrokenPipeError())
        with self.assertRaises(RuntimeError): self.call(process, Responses(process))
        self.assertTrue(process.killed); self.assertFalse(tts._lock.locked())

    def test_stop_resets_state_even_if_cleanup_times_out(self):
        process = FakeProcess(); process.wait = MagicMock(side_effect=subprocess.TimeoutExpired("worker", 10))
        with patch.object(tts, "_process", process), patch.object(tts, "_responses", queue.Queue()):
            tts._stop()
            self.assertIsNone(tts._process); self.assertIsNone(tts._responses)
        self.assertTrue(process.killed)

    def test_start_has_offline_flags_no_shell_and_isolated_response_queue(self):
        process = FakeProcess()
        with patch.object(tts, "_process", None), patch.object(tts, "_responses", None), \
             patch.object(tts, "_python", return_value="python-local"), \
             patch.object(tts.subprocess, "Popen", return_value=process) as popen, \
             patch.object(tts.threading, "Thread") as thread:
            tts._start()
            args, kwargs = popen.call_args
            self.assertEqual(args[0], ["python-local", "-u", "-m", "lessonvoice.neural_worker"])
            self.assertIs(kwargs["shell"], False)
            self.assertEqual(kwargs["env"]["HF_HUB_OFFLINE"], "1")
            self.assertEqual(kwargs["env"]["TRANSFORMERS_OFFLINE"], "1")
            self.assertEqual(kwargs["env"]["HF_HUB_DISABLE_TELEMETRY"], "1")
            self.assertIsInstance(tts._responses, queue.Queue)
            thread.assert_called_once(); thread.return_value.start.assert_called_once()
            tts._start(); self.assertEqual(popen.call_count, 1)

    def test_start_replaces_dead_worker_and_its_old_queue(self):
        old = FakeProcess(); old.killed = True
        old_responses = queue.Queue(); old_responses.put(b"stale earlier response")
        new = FakeProcess()
        with patch.object(tts, "_process", old), patch.object(tts, "_responses", old_responses), \
             patch.object(tts.subprocess, "Popen", return_value=new), patch.object(tts.threading, "Thread"):
            tts._start()
            self.assertIs(tts._process, new)
            self.assertIsNot(tts._responses, old_responses)
            self.assertTrue(tts._responses.empty())


if __name__ == "__main__": unittest.main()
