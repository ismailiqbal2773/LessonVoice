"""One-time model installation. Inference never invokes this network-enabled tool."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import urllib.request

REVISION = "c5fdb5ccb189668d56333f77ba2629f4cd7535f4"
REPOSITORY = "k2-fsa/OmniVoice"
DESTINATION = Path(__file__).resolve().parents[1] / "models" / "omnivoice"


def download() -> None:
    print("Installing offline assets (~3.3 GB). Review model and tokenizer terms in THIRD_PARTY_NOTICES.md.")
    with urllib.request.urlopen(f"https://huggingface.co/api/models/{REPOSITORY}/revision/{REVISION}?blobs=true", timeout=60) as response:
        metadata = json.load(response)
    if metadata["sha"] != REVISION:
        raise RuntimeError("Unexpected model revision.")
    for asset in metadata["siblings"]:
        name = asset["rfilename"]
        if name.endswith(".gitattributes"):
            continue
        relative = Path(name)
        if relative.is_absolute() or relative.drive or relative.root or ".." in relative.parts or ":" in name or "\\" in name:
            raise RuntimeError("Unsafe upstream asset path.")
        target = DESTINATION / relative
        target.resolve().relative_to(DESTINATION.resolve())
        target.parent.mkdir(parents=True, exist_ok=True)
        expected = asset.get("lfs", {}).get("sha256")
        blob_id = asset.get("blobId")
        def valid(path):
            with path.open("rb") as handle:
                if expected:
                    return hashlib.file_digest(handle,"sha256").hexdigest() == expected
                digest = hashlib.sha1(b"blob " + str(asset["size"]).encode() + b"\0")
                while chunk := handle.read(4*1024*1024):
                    digest.update(chunk)
                return bool(blob_id) and digest.hexdigest() == blob_id
        if target.is_file() and target.stat().st_size == asset["size"]:
            if valid(target):
                print("Present:", name, flush=True)
                continue
        temporary = target.with_suffix(target.suffix + ".partial")
        print("Downloading:", name, flush=True)
        digest = hashlib.sha256()
        with urllib.request.urlopen(f"https://huggingface.co/{REPOSITORY}/resolve/{REVISION}/{name}", timeout=120) as response, temporary.open("wb") as output:
            while chunk := response.read(4 * 1024 * 1024):
                output.write(chunk)
                digest.update(chunk)
        if temporary.stat().st_size != asset["size"] or not valid(temporary):
            raise RuntimeError(f"Downloaded asset failed integrity check: {name}")
        temporary.replace(target)
    (DESTINATION / "REVISION").write_text(REVISION, encoding="ascii")
    print("Model installation complete. Lesson text stays offline during inference.")


if __name__ == "__main__":
    download()
