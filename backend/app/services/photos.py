"""Photos: raw image bytes in, a URL under `/media` out.

No image library on purpose — the upload is validated by magic bytes and a size
cap, which is all this project needs (a real product would re-encode the file to
strip metadata and cap the dimensions).

    png  89 50 4E 47 0D 0A 1A 0A
    jpg  FF D8 FF
    webp "RIFF" ….  "WEBP"
"""

from pathlib import Path
from uuid import UUID

from app.core.config import settings

SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpg"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
)

# A folder per kind so a path never leaves its collection.
COLLECTIONS = {"venues": "venues", "courts": "courts"}


class PhotoError(ValueError):
    """The upload is not an image we accept, or it is too big."""


def sniff(data: bytes) -> str | None:
    """Return the extension for a supported image, or None."""
    for signature, extension in SIGNATURES:
        if data.startswith(signature):
            return extension
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def folder(kind: str) -> Path:
    try:
        name = COLLECTIONS[kind]
    except KeyError as exc:  # pragma: no cover - programming error
        raise PhotoError(f"unknown photo collection: {kind}") from exc
    path = Path(settings.media_root) / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _files(kind: str, public_id: UUID | str) -> list[Path]:
    return sorted(folder(kind).glob(f"{public_id}.*"))


def store(kind: str, public_id: UUID | str, data: bytes) -> str:
    """Save the upload and return its public URL. Raises PhotoError on junk."""
    if not data:
        raise PhotoError("the upload is empty")
    if len(data) > settings.max_photo_bytes:
        raise PhotoError(
            f"the photo is larger than {settings.max_photo_bytes // 1000} kB"
        )
    extension = sniff(data)
    if extension is None:
        raise PhotoError("only PNG, JPEG, GIF or WebP images are accepted")
    clear(kind, public_id)  # one photo per venue/court, keep the newest
    target = folder(kind) / f"{public_id}.{extension}"
    target.write_bytes(data)
    return f"{settings.media_url}/{kind}/{target.name}"


def clear(kind: str, public_id: UUID | str) -> int:
    """Delete every stored photo of that venue/court. Returns how many files went."""
    removed = 0
    for path in _files(kind, public_id):
        path.unlink()
        removed += 1
    return removed


def path_of(url: str) -> Path | None:
    """Where a URL we handed out lives on disk (None for an external link)."""
    prefix = f"{settings.media_url}/"
    if not url or not url.startswith(prefix):
        return None
    relative = url[len(prefix) :]
    if ".." in relative:
        return None
    return Path(settings.media_root) / relative
