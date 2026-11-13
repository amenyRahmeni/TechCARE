from io import BytesIO
import warnings

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError


def clean_photo(upload):
    """Decode and re-encode a bounded raster; never keep its name or metadata."""
    if not upload:
        return None
    if upload.size > 5 * 1024 * 1024:
        raise ValidationError("La photo doit faire au maximum 5 Mo.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(upload) as source:
                if source.format not in ("JPEG", "PNG", "WEBP"):
                    raise ValidationError("Choisissez une image JPEG, PNG ou WebP.")
                if source.width * source.height > 20_000_000:
                    raise ValidationError("La photo est trop grande (20 mégapixels maximum).")
                source.load()
                raster = ImageOps.exif_transpose(source).convert("RGB")
                raster.thumbnail((1800, 1800))
                result = BytesIO()
                raster.save(result, "JPEG", quality=86, optimize=True)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValidationError("Cette image est invalide ou trop grande.") from None
    return ContentFile(result.getvalue(), name="photo.jpg")
