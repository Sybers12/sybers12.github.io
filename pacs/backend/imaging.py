import io

import numpy as np
from PIL import Image
from pydicom import Dataset
from pydicom.pixel_data_handlers.util import apply_modality_lut


def get_frame(ds: Dataset, frame_index: int = 0) -> np.ndarray:
    """Return one frame as float pixel values after modality LUT (rescale)."""
    pixels = ds.pixel_array
    if pixels.ndim == 3:
        frame_index = max(0, min(frame_index, pixels.shape[0] - 1))
        pixels = pixels[frame_index]
    return apply_modality_lut(pixels.astype(np.float64), ds).astype(np.float64)


def render_png(pixels: np.ndarray, window_center: float, window_width: float,
               invert: bool = False) -> bytes:
    """Apply a linear window/level transform and return PNG bytes."""
    if window_width <= 0:
        window_width = float(pixels.max() - pixels.min()) or 1.0
    if window_center == 0 and window_width <= 0:
        window_center = float((pixels.max() + pixels.min()) / 2.0)

    low = window_center - window_width / 2.0
    high = window_center + window_width / 2.0
    span = high - low
    if span <= 0:
        span = 1.0
    scaled = (pixels - low) * (255.0 / span)
    image = np.clip(scaled, 0.0, 255.0).astype(np.uint8)
    if invert:
        image = 255 - image
    buffer = io.BytesIO()
    Image.fromarray(image, mode="L").save(buffer, format="PNG")
    return buffer.getvalue()


def thumbnail_png(ds: Dataset, max_size: int = 128) -> bytes:
    """Small preview image with default windowing, for series thumbnails."""
    pixels = get_frame(ds, 0)
    wc = 0.0
    ww = 0.0
    center = getattr(ds, "WindowCenter", None)
    width = getattr(ds, "WindowWidth", None)
    if center is not None and width is not None:
        try:
            wc = float(center[0] if isinstance(center, (list, tuple)) else center)
            ww = float(width[0] if isinstance(width, (list, tuple)) else width)
        except (TypeError, ValueError):
            pass
    png = render_png(pixels, wc, ww, invert=False)
    image = Image.open(io.BytesIO(png))
    image.thumbnail((max_size, max_size))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
