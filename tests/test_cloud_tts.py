"""Cloud contract tests: no paid request or real credentials."""
import json
import struct
import unittest
from unittest.mock import patch, MagicMock
from urllib.error import URLError
from lessonvoice.cloud_tts import synthesise
from lessonvoice.core import validate_wav

class CloudTests(unittest.TestCase):
    def options(self):
        return {'apiKey':'test-key-only', 'voiceId':'voice123', 'consent':True}
    def test_requires_explicit_consent_and_valid_credentials(self):
        for change in ({'consent':False},{'apiKey':''},{'voiceId':'../bad'}):
            with patch('urllib.request.urlopen') as call:
                with self.assertRaises(ValueError):
                    synthesise('Hello', 'en', 150, {**self.options(), **change})
                call.assert_not_called()
    def test_pcm_contract_wav_and_urdu(self):
        response=MagicMock();response.__enter__.return_value.read.return_value=struct.pack('<2400h', *([-1000,1000]*1200))
        with patch('urllib.request.urlopen',return_value=response) as call:
            audio=synthesise('سلام', 'ur', 220, self.options())
        self.assertEqual(validate_wav(audio)['sampleRate'],24000)
        request=call.call_args.args[0];body=json.loads(request.data)
        self.assertEqual(body['model_id'],'eleven_v3');self.assertEqual(body['language_code'],'ur')
        self.assertEqual(body['voice_settings']['speed'],1.2)
        self.assertTrue(request.full_url.endswith('?output_format=pcm_24000'))
    def test_provider_errors_do_not_leak_key_or_response(self):
        with patch('urllib.request.urlopen',side_effect=URLError('test-key-only')):
            with self.assertRaises(RuntimeError) as error:
                synthesise('Hello','en',150,self.options())
        self.assertNotIn('test-key-only',str(error.exception))
    def test_bad_pcm_is_rejected(self):
        response=MagicMock();response.__enter__.return_value.read.return_value=b'bad'
        with patch('urllib.request.urlopen',return_value=response):
            with self.assertRaises(RuntimeError):synthesise('Hello','en',150,self.options())
