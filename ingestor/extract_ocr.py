"""Tesseract OCR with deskew and threshold preprocessing."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageOps

# Words at or below this confidence are flagged for a person to review.
LOW_WORD_CONFIDENCE = 50.0
# A page/record average below this is marked for review.
LOW_PAGE_CONFIDENCE = 65.0
# PSM 3 (fully automatic) keeps form headers that PSM 6 sometimes drops.
TESSERACT_CONFIG = "--oem 3 --psm 3"


class OcrUnavailable(RuntimeError):
    """Tesseract is not installed on this machine."""


@dataclass
class OcrWord:
    text: str
    conf: float
    left: int
    top: int
    width: int
    height: int
    line_num: int
    page: int


@dataclass
class OcrPage:
    page: int
    text: str
    confidence: float
    words: list[OcrWord] = field(default_factory=list)
    image: Image.Image | None = None
    preprocessed: Image.Image | None = None
    deskew_degrees: float = 0.0


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def _require_tesseract() -> None:
    if not tesseract_available():
        raise OcrUnavailable(
            "Tesseract OCR is not installed. On Debian/Ubuntu run: "
            "sudo apt-get install -y tesseract-ocr tesseract-ocr-eng"
        )


def _as_grayscale(image: Image.Image) -> Image.Image:
    if image.mode == "RGBA":
        background = Image.new("RGBA", image.size, (255, 255, 255, 255))
        image = Image.alpha_composite(background, image)
    return ImageOps.grayscale(image)


def otsu_threshold(gray: np.ndarray) -> int:
    """Compute an Otsu threshold for a uint8 grayscale array."""
    hist, _ = np.histogram(gray.flatten(), bins=256, range=(0, 256))
    total = int(gray.size)
    sum_total = float(np.dot(np.arange(256), hist))
    sum_b = 0.0
    w_b = 0
    max_var = 0.0
    thresh = 127
    for i in range(256):
        w_b += int(hist[i])
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += i * float(hist[i])
        m_b = sum_b / w_b
        m_f = (sum_total - sum_b) / w_f
        var = w_b * w_f * (m_b - m_f) ** 2
        if var > max_var:
            max_var = var
            thresh = i
    return int(thresh)


def _projection_variance(binary: np.ndarray) -> float:
    # More variance in the row-wise ink density usually means the lines are level.
    projection = binary.mean(axis=1)
    return float(projection.var())


def deskew(image: Image.Image, max_angle: float = 5.0, step: float = 0.25) -> tuple[Image.Image, float]:
    """Rotate a grayscale page so text lines sit closer to horizontal."""
    gray = _as_grayscale(image)
    arr = np.asarray(gray, dtype=np.uint8)
    # Work on a smaller copy so the angle search stays cheap.
    scale = 400 / max(arr.shape[0], 1)
    if scale < 1:
        small = gray.resize(
            (max(1, int(gray.width * scale)), max(1, int(gray.height * scale))),
            Image.Resampling.BILINEAR,
        )
    else:
        small = gray
    small_arr = np.asarray(small, dtype=np.uint8)
    thresh = otsu_threshold(small_arr)
    binary = (small_arr < thresh).astype(np.uint8)

    best_angle = 0.0
    best_score = -1.0
    angle = -max_angle
    while angle <= max_angle + 1e-9:
        rotated = Image.fromarray(binary * 255).rotate(
            angle, resample=Image.Resampling.BILINEAR, fillcolor=0
        )
        score = _projection_variance(np.asarray(rotated, dtype=np.uint8) > 127)
        if score > best_score:
            best_score = score
            best_angle = angle
        angle += step

    if abs(best_angle) < 0.1:
        return gray, 0.0
    # Rotate the full-resolution grayscale, filling with paper white.
    deskewed = gray.rotate(
        best_angle,
        resample=Image.Resampling.BICUBIC,
        expand=False,
        fillcolor=255,
    )
    return deskewed, best_angle


def preprocess(image: Image.Image) -> tuple[Image.Image, float]:
    """Deskew, boost contrast, and apply an Otsu threshold for Tesseract."""
    deskewed, angle = deskew(image)
    # A light contrast stretch helps faded typewriter ink.
    stretched = ImageOps.autocontrast(deskewed, cutoff=1)
    arr = np.asarray(stretched, dtype=np.uint8)
    thresh = otsu_threshold(arr)
    # Bias the threshold slightly toward keeping faint ink.
    cut = max(0, thresh - 8)
    binary = np.where(arr < cut, 0, 255).astype(np.uint8)
    out = Image.fromarray(binary, mode="L")
    # Close single-pixel gaps in glyphs without smearing the page.
    out = out.filter(ImageFilter.MedianFilter(size=3))
    return out, angle


def _pdf_to_images(path: Path, dpi: int = 200) -> list[Image.Image]:
    """Rasterize a PDF with pdftoppm (poppler). Fallback: embedded images via pypdf."""
    pdftoppm = shutil.which("pdftoppm")
    if pdftoppm:
        with tempfile.TemporaryDirectory(prefix="ingestor-pdf-") as tmp:
            prefix = Path(tmp) / "page"
            result = subprocess.run(
                [pdftoppm, "-png", "-r", str(dpi), str(path), str(prefix)],
                capture_output=True,
                text=True,
                check=False,
            )
            pages = sorted(Path(tmp).glob("page*.png"))
            if result.returncode != 0 or not pages:
                raise RuntimeError(
                    f"pdftoppm failed for {path.name}: {result.stderr.strip() or result.stdout.strip()}"
                )
            return [Image.open(p).convert("RGB") for p in pages]
    # Fallback for environments without poppler: pull embedded images only.
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    images: list[Image.Image] = []
    for page in reader.pages:
        for image in page.images:
            images.append(image.image.convert("RGB"))
    if not images:
        raise RuntimeError(
            f"Cannot rasterize {path.name}: pdftoppm is not installed and the PDF has no embedded images."
        )
    return images


def load_pages(path: str | Path) -> list[Image.Image]:
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        return _pdf_to_images(path)
    return [Image.open(path).convert("RGB")]


def _mean_confidence(words: list[OcrWord]) -> float:
    scored = [w.conf for w in words if w.text.strip() and w.conf >= 0]
    if not scored:
        return 0.0
    return float(sum(scored) / len(scored))


def ocr_image(image: Image.Image, page: int = 1) -> OcrPage:
    """Preprocess one page and run Tesseract, returning text and word boxes."""
    _require_tesseract()
    import pytesseract

    preprocessed, angle = preprocess(image)
    data = pytesseract.image_to_data(
        preprocessed,
        lang="eng",
        config=TESSERACT_CONFIG,
        output_type=pytesseract.Output.DICT,
    )
    words: list[OcrWord] = []
    n = len(data["text"])
    for i in range(n):
        text = (data["text"][i] or "").strip()
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1.0
        if not text and conf < 0:
            continue
        if not text:
            continue
        words.append(
            OcrWord(
                text=text,
                conf=conf,
                left=int(data["left"][i]),
                top=int(data["top"][i]),
                width=int(data["width"][i]),
                height=int(data["height"][i]),
                line_num=int(data["line_num"][i] or 0),
                page=page,
            )
        )
    # Rebuild line-aware text so the extracted view stays readable.
    lines: list[str] = []
    current: list[str] = []
    current_line = None
    for word in words:
        if current_line is not None and word.line_num != current_line:
            lines.append(" ".join(current))
            current = []
        current_line = word.line_num
        current.append(word.text)
    if current:
        lines.append(" ".join(current))
    text = "\n".join(lines).strip()
    if not text:
        text = pytesseract.image_to_string(
            preprocessed, lang="eng", config=TESSERACT_CONFIG
        ).strip()
    return OcrPage(
        page=page,
        text=text,
        confidence=_mean_confidence(words),
        words=words,
        image=image,
        preprocessed=preprocessed,
        deskew_degrees=angle,
    )


def ocr_file(path: str | Path) -> list[OcrPage]:
    pages = load_pages(path)
    return [ocr_image(image, page=i + 1) for i, image in enumerate(pages)]


def low_confidence_words(page: OcrPage, threshold: float = LOW_WORD_CONFIDENCE) -> list[OcrWord]:
    return [w for w in page.words if w.text.strip() and 0 <= w.conf <= threshold]
