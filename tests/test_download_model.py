"""Installer path/integrity tests; HTTPS is mocked and no model is loaded."""
from contextlib import redirect_stdout
import hashlib
import importlib.util
from io import BytesIO, StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

_path = Path(__file__).resolve().parents[1] / "tools/download_model.py"
_spec = importlib.util.spec_from_file_location("lessonvoice_installer_under_test", _path)
installer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(installer)


def metadata(assets, revision=None):
    return BytesIO(json.dumps({"sha": revision or installer.REVISION, "siblings": assets}).encode())


def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


class InstallerTests(unittest.TestCase):
    def test_revision_mismatch_stops_before_assets(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(installer, "DESTINATION", Path(temp)), \
             patch.object(installer.urllib.request, "urlopen", return_value=metadata([], "unexpected")) as fetch, redirect_stdout(StringIO()):
            with self.assertRaisesRegex(RuntimeError, "revision"): installer.download()
            self.assertEqual(fetch.call_count, 1)

    def test_windows_and_posix_unsafe_paths_rejected(self):
        for name in ("../escape", "/absolute", "D:escape", "dir\\escape", "config.json:stream"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp, \
                 patch.object(installer, "DESTINATION", Path(temp)), \
                 patch.object(installer.urllib.request, "urlopen", return_value=metadata([{"rfilename": name, "size": 3}])) as fetch, redirect_stdout(StringIO()):
                with self.assertRaisesRegex(RuntimeError, "Unsafe"): installer.download()
                self.assertEqual(fetch.call_count, 1)

    def test_non_lfs_hash_and_cache_revalidation(self):
        data = b'{"sample_rate":24000}'
        asset = {"rfilename": "config.json", "size": len(data), "blobId": git_blob(data)}
        with tempfile.TemporaryDirectory() as temp, patch.object(installer, "DESTINATION", Path(temp)), \
             patch.object(installer.urllib.request, "urlopen", side_effect=[metadata([asset]), BytesIO(data), metadata([asset]), BytesIO(data), metadata([asset])]) as fetch, redirect_stdout(StringIO()):
            installer.download()
            target = Path(temp) / "config.json"
            self.assertEqual(target.read_bytes(), data)
            target.write_bytes(b"x" * len(data))
            installer.download()
            self.assertEqual(target.read_bytes(), data)
            installer.download()
            self.assertEqual(fetch.call_count, 5)
            self.assertEqual((Path(temp) / "REVISION").read_text(), installer.REVISION)

    def test_bad_lfs_digest_does_not_replace_asset(self):
        data = b"valid-model-fixture"
        asset = {"rfilename": "model.safetensors", "size": len(data), "lfs": {"sha256": hashlib.sha256(data).hexdigest()}}
        with tempfile.TemporaryDirectory() as temp, patch.object(installer, "DESTINATION", Path(temp)), \
             patch.object(installer.urllib.request, "urlopen", side_effect=[metadata([asset]), BytesIO(b"x" * len(data))]), redirect_stdout(StringIO()):
            with self.assertRaisesRegex(RuntimeError, "integrity"): installer.download()
            self.assertFalse((Path(temp) / "model.safetensors").exists())
            self.assertFalse((Path(temp) / "REVISION").exists())

    def test_missing_regular_file_hash_fails_closed(self):
        asset = {"rfilename": "config.json", "size": 3}
        with tempfile.TemporaryDirectory() as temp, patch.object(installer, "DESTINATION", Path(temp)), \
             patch.object(installer.urllib.request, "urlopen", side_effect=[metadata([asset]), BytesIO(b"abc")]), redirect_stdout(StringIO()):
            with self.assertRaisesRegex(RuntimeError, "integrity"): installer.download()
            self.assertFalse((Path(temp) / "config.json").exists())


if __name__ == "__main__": unittest.main()
