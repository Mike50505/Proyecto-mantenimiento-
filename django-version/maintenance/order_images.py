"""Validate and normalize photographs before storing them transactionally in PostgreSQL."""
import hashlib
import io
import warnings
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 25_000_000
TARGET_IMAGE_BYTES = 300 * 1024


class ImageUploadError(ValueError):
    pass


@dataclass(frozen=True)
class PreparedImage:
    content: bytes
    sha256: str
    width: int
    height: int
    content_type: str = 'image/webp'


def compress_image(image):
    """Prefer full resolution; adapt quality first, then downsize very complex photos.

    The byte limit is a target, not a reason to reject valid evidence or endlessly
    degrade it. Never upscale small photographs or reduce below a 1024px long side.
    """
    baseline = io.BytesIO()
    image.save(baseline, format='JPEG', quality=85, optimize=True)
    # Never store more bytes than the previous JPEG compression would use.
    best = (baseline.getvalue(), image.width, image.height, 'image/jpeg')
    for edge in (1600, 1280, 1024):
        if edge != 1600 and max(image.size) <= edge:
            continue
        candidate = image.copy()
        candidate.thumbnail((edge, edge), Image.Resampling.LANCZOS)
        for quality in (82, 74, 66):
            output = io.BytesIO()
            candidate.save(output, format='WEBP', quality=quality, method=6)
            data = output.getvalue()
            if len(data) < len(best[0]):
                best = (data, candidate.width, candidate.height, 'image/webp')
            if len(best[0]) <= TARGET_IMAGE_BYTES:
                return best
    return best


def prepare_image(upload):
    if upload.size > MAX_UPLOAD_BYTES:
        raise ImageUploadError('La imagen debe pesar como máximo 8 MB.')
    content = upload.read(MAX_UPLOAD_BYTES + 1)
    if not content or len(content) > MAX_UPLOAD_BYTES:
        raise ImageUploadError('Selecciona una imagen de hasta 8 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as original:
                if original.format not in {'JPEG', 'PNG', 'WEBP'}:
                    raise ImageUploadError('Usa una imagen JPG, PNG o WebP.')
                if original.width * original.height > MAX_PIXELS:
                    raise ImageUploadError('La imagen supera los 25 megapíxeles. Selecciona una de menor resolución.')
                if getattr(original, 'n_frames', 1) != 1:
                    raise ImageUploadError('Selecciona una fotografía fija, sin animación.')
                original.verify()
            with Image.open(io.BytesIO(content)) as original:
                image = ImageOps.exif_transpose(original)
                image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
                if image.mode in ('RGBA', 'LA') or 'transparency' in image.info:
                    rgba = image.convert('RGBA')
                    normalized = Image.new('RGB', rgba.size, 'white')
                    normalized.paste(rgba, mask=rgba.getchannel('A'))
                else:
                    normalized = image.convert('RGB')
                # Re-encoding discards EXIF/GPS and arbitrary uploaded metadata.
                data, width, height, content_type = compress_image(normalized)
                return PreparedImage(data, hashlib.sha256(data).hexdigest(), width, height, content_type)
    except ImageUploadError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError,
            Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ImageUploadError('No se pudo leer la imagen. Usa un archivo JPG, PNG o WebP válido.') from None
