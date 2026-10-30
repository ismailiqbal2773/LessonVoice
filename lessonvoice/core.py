"""Validation, deterministic lesson preparation and safe learning-pack exports."""
from __future__ import annotations

import base64
import binascii
import hashlib
import html
from io import BytesIO
import json
import re
import struct
from typing import Any
import wave
import zipfile

MAX_LESSON = 20_000
MAX_SECTIONS = 24
MAX_SECTION = 1_500
MAX_AUDIO_BYTES = 10 * 1024 * 1024
MAX_PACK_AUDIO = 96 * 1024 * 1024
VOICE_IDS = ("warm-female", "clear-male", "storyteller-female", "calm-male")
DEFAULT_VOICE = "warm-female"
_ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")


def text_field(value: Any, label: str, maximum: int, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text.")
    value = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not allow_empty and not value:
        raise ValueError(f"{label} cannot be empty.")
    if len(value) > maximum:
        raise ValueError(f"{label} must be {maximum:,} characters or fewer.")
    if any((ord(c) < 32 and c not in "\n\t") or 0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise ValueError(f"{label} contains unsupported control characters.")
    return value


def _list(value: Any, label: str, maximum: int) -> list:
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError(f"{label} must be a list with at most {maximum} items.")
    return value


def validate_settings(raw: Any) -> dict:
    """Validate the same speech settings for previews and full projects."""
    if not isinstance(raw, dict):
        raise ValueError("Speech settings must be an object.")
    language = raw.get("language")
    if language not in ("en", "ur"):
        raise ValueError("Choose English or Urdu.")
    rate = raw.get("rate")
    if type(rate) is not int or not 100 <= rate <= 220:
        raise ValueError("Speech rate must be a whole number from 100 to 220.")
    voice = raw.get("voice", DEFAULT_VOICE)
    if voice not in VOICE_IDS:
        raise ValueError("Choose one of the four supported voice presets.")
    return {"language": language, "rate": rate, "voice": voice}


def validate_project(raw: Any) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("Project must be an object.")
    if type(raw.get("version")) is not int or raw["version"] != 1:
        raise ValueError("Unsupported project version; expected version 1.")
    title = text_field(raw.get("title"), "Lesson title", 120)
    settings = validate_settings(raw)
    sections = []
    seen = set()
    for item in _list(raw.get("sections"), "Sections", MAX_SECTIONS):
        if not isinstance(item, dict):
            raise ValueError("Each section must be an object.")
        ident = item.get("id")
        if not isinstance(ident, str) or not _ID.fullmatch(ident) or ident in seen:
            raise ValueError("Section IDs must be unique letters, numbers, hyphens or underscores (1–64 characters).")
        seen.add(ident)
        sections.append({"id": ident, "title": text_field(item.get("title"), "Section title", 120),
                         "text": text_field(item.get("text"), "Section text", MAX_SECTION)})
    if not sections:
        raise ValueError("Add at least one lesson section.")
    if sum(len(s["text"]) for s in sections) > MAX_LESSON:
        raise ValueError("Lesson text must be 20,000 characters or fewer.")
    pronunciations = []
    seen_terms = set()
    for item in _list(raw.get("pronunciations", []), "Pronunciation rules", 30):
        if not isinstance(item, dict):
            raise ValueError("Each pronunciation rule must be an object.")
        term = text_field(item.get("term"), "Pronunciation term", 80)
        say = text_field(item.get("say"), "Pronunciation replacement", 120)
        if term in seen_terms:
            raise ValueError("Each pronunciation term can appear only once.")
        if "\n" in term or "\n" in say or "\t" in term or "\t" in say:
            raise ValueError("Pronunciation terms and replacements must be single-line text.")
        seen_terms.add(term)
        pronunciations.append({"term": term, "say": say})
    questions = []
    for item in _list(raw.get("questions", []), "Questions", 30):
        if not isinstance(item, dict):
            raise ValueError("Each question must be an object.")
        questions.append({"question": text_field(item.get("question"), "Question", 500),
                          "answer": text_field(item.get("answer"), "Answer", 1_500)})
    project = {"version": 1, "title": title, **settings,
               "sections": sections, "pronunciations": pronunciations, "questions": questions}
    # Expansion from replacements is bounded independently of original lesson length.
    spoken = spoken_sections(project)
    if any("[[" in s["text"] or "]]" in s["text"] for s in spoken):
        raise ValueError("Use plain lesson text, not [[...]] phoneme commands. Remove double brackets from spoken text.")
    if any(len(s["text"]) > 3_000 for s in spoken) or sum(len(s["text"]) for s in spoken) > 30_000:
        raise ValueError("Pronunciation replacements make the spoken lesson too long. Shorten them.")
    return project


def segment(raw_text: Any) -> list[dict]:
    text = text_field(raw_text, "Lesson text", MAX_LESSON)
    chunks: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text):
        remaining = paragraph.strip()
        while remaining:
            end = min(len(remaining), MAX_SECTION)
            if end < len(remaining):
                boundary = remaining.rfind(" ", 750, end)
                if boundary > 0:
                    end = boundary
            chunks.append(remaining[:end].strip())
            remaining = remaining[end:].strip()
    if len(chunks) > MAX_SECTIONS:
        raise ValueError("This creates more than 24 sections. Combine short paragraphs or shorten the lesson.")
    return [{"id": f"section-{i:02d}-{hashlib.sha256(t.encode('utf-8')).hexdigest()[:8]}",
             "title": f"Section {i}", "text": t} for i, t in enumerate(chunks, 1)]


def spoken_text(text: str, rules: list[dict]) -> str:
    """Literal, case-sensitive simultaneous replacements; never cascading or executable."""
    if not rules:
        return text
    replacements = {r["term"]: r["say"] for r in rules}
    pattern = re.compile("|".join(re.escape(t) for t in sorted(replacements, key=len, reverse=True)))
    return pattern.sub(lambda match: replacements[match.group(0)], text)


def spoken_sections(project: dict) -> list[dict]:
    return [{"id": s["id"], "text": spoken_text(s["text"], project["pronunciations"])}
            for s in project["sections"]]


def audio_signature(language: str, rate: int, voice: str, text: str) -> str:
    payload = json.dumps([language, rate, voice, text], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_wav(data: bytes) -> dict:
    if not isinstance(data, bytes) or not 44 <= len(data) <= MAX_AUDIO_BYTES:
        raise ValueError("Each audio file must be a valid WAV of 10 MB or less.")
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("Audio must be an uncompressed PCM WAV file.")
    try:
        with wave.open(BytesIO(data), "rb") as reader:
            channels, width, rate, frames = reader.getnchannels(), reader.getsampwidth(), reader.getframerate(), reader.getnframes()
            if reader.getcomptype() != "NONE" or channels != 1 or width != 2 or rate not in (22_050, 24_000):
                raise ValueError("Audio must use mono 22,050 or 24,000 Hz 16-bit PCM WAV settings.")
            duration = frames / rate
            if not .05 <= duration <= 300:
                raise ValueError("Section audio must be between 0.05 seconds and five minutes.")
            payload = reader.readframes(frames)
            if len(payload) != frames * channels * width:
                raise ValueError("Audio is truncated. Generate this section again.")
            # A nonzero constant is a DC offset, not useful speech. A tiny
            # alternating signal is likewise not evidence of audible output.
            minimum, maximum = 32767, -32768
            for (sample,) in struct.iter_unpack("<h", payload):
                minimum = min(minimum, sample)
                maximum = max(maximum, sample)
            if maximum - minimum <= 16:
                raise ValueError("Audio is empty or silent. Generate this section again.")
            return {"durationSeconds": round(duration, 3), "sampleRate": rate, "channels": channels}
    except (wave.Error, EOFError, OverflowError) as exc:
        raise ValueError("Audio could not be read as a valid PCM WAV. Generate it again.") from exc


def export_pack(raw_project: Any, raw_audio: Any, speech_source=None) -> bytes:
    project = validate_project(raw_project)
    audio_items = _list(raw_audio, "Audio files", MAX_SECTIONS)
    expected = {s["id"]: s for s in spoken_sections(project)}
    if len(audio_items) != len(expected):
        raise ValueError("Generate current audio for every section before exporting.")
    audio_map: dict[str, tuple[bytes, dict]] = {}
    total = 0
    for item in audio_items:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ValueError("Each audio entry needs a section ID.")
        ident = item["id"]
        if ident not in expected or ident in audio_map:
            raise ValueError("Audio entries must match the lesson's unique section IDs.")
        signature = audio_signature(project["language"], project["rate"], project["voice"], expected[ident]["text"])
        if item.get("signature") != signature:
            raise ValueError("Audio is out of date. Regenerate changed sections before exporting.")
        encoded = item.get("data")
        if not isinstance(encoded, str) or len(encoded) > (MAX_AUDIO_BYTES * 4 // 3 + 8):
            raise ValueError("Audio data is invalid or too large.")
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("Audio data is not valid base64.") from exc
        total += len(data)
        if total > MAX_PACK_AUDIO:
            raise ValueError("Audio exceeds the 96 MB pack limit. Split the lesson into smaller packs.")
        audio_map[ident] = (data, validate_wav(data))

    source_lines = [project["title"], ""]
    spoken_lines = [project["title"], ""]
    question_lines = [project["title"], "Comprehension questions (teacher-authored)", ""]
    answers = [project["title"], "ANSWER KEY — for teacher review before sharing", ""]
    rendered = []
    manifest = {"format": "lessonvoice-pack", "version": 1, "title": project["title"],
                "language": project["language"], "rate": project["rate"], "voice": project["voice"],
                "pronunciations": project["pronunciations"], "sections": [],
                "questions": project["questions"],
                "notice": "Synthetic speech. Teacher review required. This ZIP includes an answer key. The signatures bind text/settings to supplied audio metadata, not speech-recognition verification."}
    if speech_source is not None:
        if not isinstance(speech_source, dict) or speech_source.get('provider') not in ('local', 'elevenlabs'):
            raise ValueError('Invalid speech source.')
        provider = speech_source['provider']
        voice_id = speech_source.get('voiceId', '')
        if not isinstance(voice_id, str) or len(voice_id) > 100 or any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-' for c in voice_id):
            raise ValueError('Invalid speech source voice ID.')
        manifest['speechSource'] = {'provider':provider, 'model':'eleven_v3' if provider == 'elevenlabs' else 'OmniVoice',
                                    'voiceId':voice_id if provider == 'elevenlabs' else project['voice'],
                                    'notice':'User-supplied generation metadata; not an audio identity attestation.'}
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, section in enumerate(project["sections"], 1):
            ident = section["id"]
            spoken = expected[ident]["text"]
            filename = f"audio/section-{index:02d}.wav"
            data, details = audio_map[ident]
            archive.writestr(filename, data)
            source_lines += [f"{index}. {section['title']}", section["text"], ""]
            spoken_lines += [f"{index}. {section['title']}", spoken, ""]
            manifest["sections"].append({**section, "spokenText": spoken, "audio": filename,
                                         "signature": audio_signature(project["language"], project["rate"], project["voice"], spoken), **details})
            rendered.append(f'<section><h2>{index}. {html.escape(section["title"])}</h2><audio controls preload="none" src="{filename}"></audio><p dir="auto">{html.escape(section["text"])}</p></section>')
        for index, question in enumerate(project["questions"], 1):
            question_lines += [f"{index}. {question['question']}", ""]
            answers += [f"{index}. {question['question']}", question["answer"], ""]
        safe_questions = "".join(f'<li dir="auto">{html.escape(q["question"])}</li>' for q in project["questions"])
        page = f'''<!doctype html><html lang="{project['language']}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; media-src 'self' file:; base-uri 'none'; form-action 'none'"><title>{html.escape(project['title'])}</title><style>body{{max-width:800px;margin:40px auto;padding:0 20px;font:18px/1.7 system-ui;color:#172b35;background:#faf9f5}}section{{padding:22px 0;border-bottom:1px solid #bac7cc}}audio{{width:100%}}p{{white-space:pre-wrap;overflow-wrap:anywhere}}h1,h2{{line-height:1.3}}.note{{font-size:14px}}</style></head><body><h1 dir="auto">{html.escape(project['title'])}</h1><p class="note">Synthetic lesson audio · {html.escape(project['language'])} · Teacher review required</p>{''.join(rendered)}<h2>Questions</h2><ol>{safe_questions}</ol><p class="note">This learning pack includes answer-key.txt for the teacher. Remove that file and the answers in manifest.json before distributing to learners if answers should be withheld.</p></body></html>'''
        archive.writestr("index.html", page.encode("utf-8"))
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))
        for filename, lines in [("original-transcript.txt", source_lines), ("spoken-transcript.txt", spoken_lines), ("questions.txt", question_lines), ("answer-key.txt", answers)]:
            archive.writestr(filename, "\n".join(lines).encode("utf-8"))
    return output.getvalue()
