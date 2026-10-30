"""Private CPU worker; local model files only, without cloud fallback."""
from __future__ import annotations
import base64
import contextlib
from io import BytesIO
import json
import os
from pathlib import Path
import sys
import socket

os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1', DO_NOT_TRACK='1')
def _deny_network(*args, **kwargs):
    raise OSError('Network access is disabled in the speech worker.')

socket.create_connection = _deny_network
socket.socket.connect = _deny_network
socket.socket.connect_ex = _deny_network
socket.getaddrinfo = _deny_network

PRESETS = {
    'warm-female': ('female, middle-aged, moderate pitch', 101),
    'clear-male': ('male, young adult, moderate pitch', 202),
    'storyteller-female': ('female, young adult, high pitch', 303),
    'calm-male': ('male, middle-aged, low pitch', 404),
}


def main():
    model = None
    for line in sys.stdin.buffer:
        if len(line) > 65536:
            break
        request_id = None
        try:
            request = json.loads(line)
            request_id = request.get('requestId')
            if not isinstance(request_id,str) or len(request_id)!=32:
                raise ValueError('Invalid request identity')
            text, language, rate, voice = (request[k] for k in ('text','language','rate','voice'))
            if not isinstance(text,str) or not text.strip() or len(text)>3000 or language not in ('en','ur') or type(rate) is not int or not 100<=rate<=220 or voice not in PRESETS:
                raise ValueError('Invalid request')
            with contextlib.redirect_stdout(sys.stderr):
                import numpy as np
                import soundfile as sf
                import torch
                from omnivoice import OmniVoice, OmniVoiceGenerationConfig
                if model is None:
                    torch.set_num_threads(max(1,min(4,os.cpu_count() or 1)))
                    torch.set_num_interop_threads(1)
                    directory = Path(__file__).resolve().parents[1] / 'models' / 'omnivoice'
                    model = OmniVoice.from_pretrained(str(directory),device_map='cpu',dtype=torch.float32,
                                                     local_files_only=True,trust_remote_code=False,load_asr=False)
                    model.eval()
                instruct,seed = PRESETS[voice]
                torch.manual_seed(seed)
                with torch.inference_mode():
                    audio = model.generate(text=text,language=language,instruct=instruct,speed=rate/150,
                                           generation_config=OmniVoiceGenerationConfig(num_step=64))[0]
                audio = np.asarray(audio,dtype=np.float32).reshape(-1)
                if not np.all(np.isfinite(audio)) or not 1200<=len(audio)<=24000*210:
                    raise ValueError('Invalid audio output')
                output = BytesIO()
                sf.write(output,audio,24000,format='WAV',subtype='PCM_16')
                result = {'audio':base64.b64encode(output.getvalue()).decode('ascii')}
        except Exception:
            result = {'error':'Offline neural generation failed'}
        result['requestId'] = request_id
        print(json.dumps(result),flush=True)


if __name__ == '__main__':
    main()
