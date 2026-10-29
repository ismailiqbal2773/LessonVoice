"""Loopback-only stateless HTTP API for LessonVoice."""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import BoundedSemaphore
from typing import Any

from .core import export_pack, segment, spoken_sections, validate_project, validate_settings, validate_wav

ROOT = Path(__file__).resolve().parent.parent
MAX_REQUEST = 132 * 1024 * 1024
_synthesis_lock = BoundedSemaphore(1)


def engine_status() -> dict:
    try:
        from .tts import engine_status as status
        return status()
    except ImportError:
        return {"name": "Local speech engine", "available": False, "languages": [],
                "message": "Speech engine is not installed. Follow the setup instructions."}


def synthesise(text: str, language: str, rate: int, voice: str) -> bytes:
    from .tts import synthesise as render
    return render(text, language, rate, voice)


class Handler(BaseHTTPRequestHandler):
    server_version = "LessonVoice/1.0"

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(30)

    def log_message(self, *_: Any) -> None:
        pass

    def trusted(self) -> bool:
        hosts = (f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}")
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin")
        return host in hosts and (origin is None or origin == f"http://{host}")

    def reply(self, code: int, data: Any, content_type: str = "application/json", *, filename: str | None = None) -> None:
        body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type + ("; charset=utf-8" if content_type.startswith("text/") or content_type == "application/json" else ""))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        try:
            if self.command != "HEAD":
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self) -> None:
        if not self.trusted():
            return self.reply(403, {"error": "Open LessonVoice using its local URL."})
        if self.path == "/api/health":
            try:
                return self.reply(200, {"ok": True, "engine": engine_status()})
            except Exception:
                return self.reply(503, {"error": "The local speech engine could not be checked. Review its setup and retry."})
        routes = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"), "/style.css": ("style.css", "text/css")}
        if self.path not in routes:
            return self.reply(404, {"error": "Not found."})
        file, kind = routes[self.path]
        try:
            body = (ROOT / "web" / file).read_bytes()
        except OSError:
            return self.reply(503, {"error": "The interface files are missing. Reinstall the complete application folder."})
        self.reply(200, body, kind)

    def do_POST(self) -> None:
        if not self.trusted():
            return self.reply(403, {"error": "Cross-origin requests are not allowed."})
        if self.path not in ("/api/segment", "/api/spoken", "/api/audio", "/api/voice-preview", "/api/export"):
            return self.reply(404, {"error": "Not found."})
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            return self.reply(415, {"error": "Send application/json."})
        if self.headers.get("Transfer-Encoding"):
            return self.reply(400, {"error": "Chunked request bodies are not supported."})
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self.reply(400, {"error": "Invalid request length."})
        limit = MAX_REQUEST if self.path == "/api/export" else 300_000
        if not 0 < size <= limit:
            # Drain only a bounded, modest rejected body. Closing a socket with
            # unread request data can reset it on Windows before the caller
            # receives the useful 413 response.
            if 0 < size <= 1_048_576:
                self.rfile.read(size)
            return self.reply(413, {"error": "Request is empty or exceeds the permitted size."})
        try:
            body = self.rfile.read(size)
            if len(body) != size:
                raise ValueError("The request was incomplete. Try again.")
            obj = json.loads(body, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Invalid JSON number.")))
            if not isinstance(obj, dict):
                raise ValueError("Expected a JSON object.")
            if self.path == "/api/segment":
                return self.reply(200, {"sections": segment(obj.get("text"))})
            if self.path == "/api/voice-preview":
                settings = validate_settings(obj)
                spoken = {"en": "Welcome to LessonVoice. Let us learn something new together.",
                          "ur": "لیسن وائس میں خوش آمدید۔ آئیے مل کر کچھ نیا سیکھتے ہیں۔"}[settings["language"]]
            else:
                project = validate_project(obj.get("project"))
                if self.path == "/api/spoken":
                    return self.reply(200, {"sections": spoken_sections(project)})
                if self.path == "/api/export":
                    return self.reply(200, export_pack(project, obj.get("audio")), "application/zip", filename="lessonvoice-pack.zip")
                section_id = obj.get("sectionId")
                sections = {s["id"]: s["text"] for s in spoken_sections(project)}
                if not isinstance(section_id, str) or section_id not in sections:
                    raise ValueError("Select a valid section to generate.")
                spoken = sections[section_id]
                settings = project
            engine = engine_status()
            if not engine.get("available"):
                return self.reply(503, {"error": engine.get("message", "This language is not available in the installed local speech engine.")})
            if settings["language"] not in engine.get("languages", []):
                return self.reply(503, {"error": "The selected language is not available in the installed offline speech engine."})
            if not _synthesis_lock.acquire(blocking=False):
                return self.reply(503, {"error": "Another section is generating. Wait for it to finish and try again."})
            try:
                audio = synthesise(spoken, settings["language"], settings["rate"], settings["voice"])
                validate_wav(audio)
            finally:
                _synthesis_lock.release()
            return self.reply(200, audio, "audio/wav")
        except (ValueError, UnicodeDecodeError) as exc:
            return self.reply(400, {"error": str(exc)[:250]})
        except TimeoutError:
            return self.reply(503, {"error": "Audio generation timed out. Try a shorter section."})
        except RuntimeError:
            return self.reply(503, {"error": "The local speech engine could not generate audio. Check its setup and try a shorter section."})
        except Exception:
            return self.reply(500, {"error": "Processing failed. Check the local speech setup and try again."})

    def method_not_allowed(self) -> None:
        if not self.trusted():
            return self.reply(403, {"error": "Open LessonVoice using its local URL."})
        return self.reply(405, {"error": "This endpoint supports GET and POST requests only."})

    do_HEAD = method_not_allowed
    do_PUT = method_not_allowed
    do_PATCH = method_not_allowed
    do_DELETE = method_not_allowed
    do_OPTIONS = method_not_allowed


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LessonVoice on your own computer.")
    parser.add_argument("--port", type=int, default=8775)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"LessonVoice is ready: http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
