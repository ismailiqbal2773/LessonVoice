"""Bounded persistent offline neural speech worker."""
from __future__ import annotations
import atexit
import base64
import importlib.util
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import uuid

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / 'models' / 'omnivoice'
VOICES = ('warm-female', 'clear-male', 'storyteller-female', 'calm-male')
_lock = threading.Lock()
_process = None
_responses = None


def _python():
    candidate = ROOT / '.neural-venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    return str(candidate) if candidate.is_file() else sys.executable


def engine_status():
    assets = ('config.json','model.safetensors','tokenizer.json','tokenizer_config.json',
              'audio_tokenizer/config.json','audio_tokenizer/model.safetensors','audio_tokenizer/preprocessor_config.json','REVISION')
    runtime = _python() != sys.executable or importlib.util.find_spec('omnivoice') is not None
    available = runtime and all((MODEL / item).is_file() for item in assets)
    return {'name':'OmniVoice · offline neural','available':available,'languages':['en','ur'] if available else [],'voices':list(VOICES),
            'message':'Model files installed; first generation loads the model. CPU generation can take several minutes. Preview and review pronunciation before sharing.' if available else 'Offline neural setup is incomplete. Follow README setup and tools/download_model.py. No cloud or robotic fallback is used.'}


def _stop():
    global _process, _responses
    process = _process
    _process, _responses = None, None
    if process is not None:
        try:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            pass


atexit.register(_stop)


def _start():
    global _process, _responses
    if _process is not None and _process.poll() is None:
        return
    environment = dict(os.environ, HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1', DO_NOT_TRACK='1', GRADIO_ANALYTICS_ENABLED='False')
    _responses = queue.Queue()
    _process = subprocess.Popen([_python(),'-u','-m','lessonvoice.neural_worker'], cwd=ROOT, stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=environment,shell=False,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    process,responses = _process,_responses
    def read():
        try:
            while line := process.stdout.readline(15*1024*1024):
                responses.put(line)
        finally:
            responses.put(None)
    threading.Thread(target=read,daemon=True).start()


def synthesise(text, language, rate, voice='warm-female'):
    if not isinstance(text,str) or not text.strip() or len(text)>3000 or language not in ('en','ur') or type(rate) is not int or not 100<=rate<=220 or voice not in VOICES:
        raise ValueError('Invalid speech text or settings.')
    if not engine_status()['available']:
        raise RuntimeError('Offline neural model setup is incomplete. Follow the README installation steps.')
    if not _lock.acquire(blocking=False):
        raise RuntimeError('The offline voice engine is busy. Wait for current generation.')
    try:
        _start()
        request_id = uuid.uuid4().hex
        _process.stdin.write((json.dumps({'requestId':request_id,'text':text,'language':language,'rate':rate,'voice':voice},ensure_ascii=False)+'\n').encode('utf-8'))
        _process.stdin.flush()
        response = _responses.get(timeout=840)
        if response is None:
            raise RuntimeError('Offline neural worker stopped. Verify runtime and model files.')
        result = json.loads(response)
        if not isinstance(result,dict) or result.get('requestId') != request_id:
            raise ValueError('Invalid worker response identity')
        if result.get('error'):
            raise RuntimeError('Offline neural generation failed. Verify installation or try a shorter chapter.')
        from .core import validate_wav
        audio = base64.b64decode(result['audio'],validate=True)
        validate_wav(audio)
        return audio
    except queue.Empty as exc:
        _stop()
        raise RuntimeError('Generation exceeded 14 minutes. Split this chapter into shorter sections.') from exc
    except (OSError,ValueError,KeyError,TypeError,RuntimeError) as exc:
        _stop()
        raise RuntimeError('Offline neural worker failed. Verify installation and retry.') from exc
    finally:
        _lock.release()
