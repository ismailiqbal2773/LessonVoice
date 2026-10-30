"""Explicit opt-in ElevenLabs adapter; credentials exist only for a request."""
import json
import re
import urllib.request
import urllib.error
import wave
from io import BytesIO


def synthesise(text, language, rate, options):
    if not isinstance(options, dict):
        raise ValueError('Cloud speech settings are required.')
    key, voice = options.get('apiKey', ''), options.get('voiceId', '')
    if not isinstance(key, str) or not 10 <= len(key) <= 512 or any(c.isspace() for c in key):
        raise ValueError('Enter a valid ElevenLabs API key in speech settings.')
    if not isinstance(voice, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', voice):
        raise ValueError('Enter a valid ElevenLabs voice ID.')
    if options.get('consent') is not True:
        raise ValueError('Confirm that spoken lesson text may be sent to ElevenLabs.')
    payload = {'text': text, 'model_id': 'eleven_v3', 'language_code': language,
               'voice_settings': {'stability': 0.5, 'similarity_boost': 0.75, 'speed': max(0.7, min(1.2, rate / 150))}}
    request = urllib.request.Request(
        'https://api.elevenlabs.io/v1/text-to-speech/' + voice + '?output_format=pcm_24000',
        data=json.dumps(payload).encode(), headers={'xi-api-key': key, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            pcm = response.read(10 * 1024 * 1024 + 1)
    except (urllib.error.URLError, TimeoutError):
        raise RuntimeError('ElevenLabs request failed. Check key, voice access, credits and network; no local fallback was used.') from None
    if not 2400 <= len(pcm) <= 10 * 1024 * 1024 - 44 or len(pcm) % 2:
        raise RuntimeError('ElevenLabs returned invalid or oversized PCM audio.')
    output = BytesIO()
    with wave.open(output, 'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(24000); wav.writeframes(pcm)
    from .core import validate_wav
    audio = output.getvalue(); validate_wav(audio)
    return audio
