"""
extractor.py
Extracts images from PDF files using PyMuPDF.
Two functions:
- extract_images_from_pdf: basic extraction
- extract_images_smart: deduplication + size cap (use this in app.py)
"""

import fitz  # PyMuPDF
import io
from PIL import Image
import logging

logger = logging.getLogger(__name__)


def extract_images_from_pdf(pdf_bytes: bytes, source_label: str = "doc") -> list[dict]:
    """
    Extract all images from a PDF.
    Returns list of dicts with keys:
      image_bytes, page_num, index, source, label, width, height
    """
    images = []
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        img_counter = 0

        for page_num in range(len(doc)):
            page = doc[page_num]
            image_list = page.get_images(full=True)

            for img_index, img_info in enumerate(image_list):
                xref = img_info[0]
                try:
                    base_image = doc.extract_image(xref)
                    img_bytes = base_image["image"]

                    pil_img = Image.open(io.BytesIO(img_bytes))

                    # Skip tiny images (icons, decorative elements)
                    if pil_img.width < 80 or pil_img.height < 80:
                        continue

                    # Convert to RGB if needed
                    if pil_img.mode not in ("RGB", "RGBA", "L"):
                        pil_img = pil_img.convert("RGB")

                    png_buffer = io.BytesIO()
                    pil_img.save(png_buffer, format="PNG")
                    png_bytes = png_buffer.getvalue()

                    images.append({
                        "image_bytes": png_bytes,
                        "page_num": page_num,
                        "index": img_counter,
                        "source": source_label,
                        "label": f"{source_label.title()} – Page {page_num + 1}, Image {img_index + 1}",
                        "width": pil_img.width,
                        "height": pil_img.height,
                    })
                    img_counter += 1

                except Exception as e:
                    logger.warning(f"Skipping image xref={xref} on page {page_num}: {e}")
                    continue

        doc.close()
        logger.info(f"Extracted {len(images)} images from {source_label} PDF")

    except Exception as e:
        logger.error(f"Failed to extract images from {source_label} PDF: {e}")

    return images


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract all text from a PDF as a single string."""
    text = ""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page in doc:
            text += page.get_text()
        doc.close()
    except Exception as e:
        logger.error(f"Text extraction failed: {e}")
    return text


def get_pdf_page_count(pdf_bytes: bytes) -> int:
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        count = len(doc)
        doc.close()
        return count
    except Exception:
        return 0


def extract_images_smart(pdf_bytes: bytes, source_label: str = "doc", max_images: int = 60) -> list[dict]:
    """
    Smart extraction with deduplication and image cap.
    Use this in app.py instead of extract_images_from_pdf.

    Deduplication key: (width, height, byte_length) — skips repeated logo/branding images.
    Caps at max_images to prevent memory issues with large PDFs.
    """
    images = []
    seen_sizes = set()

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        img_counter = 0

        for page_num in range(len(doc)):
            if img_counter >= max_images:
                break

            page = doc[page_num]
            image_list = page.get_images(full=True)

            for img_index, img_info in enumerate(image_list):
                if img_counter >= max_images:
                    break

                xref = img_info[0]
                try:
                    base_image = doc.extract_image(xref)
                    img_bytes_raw = base_image["image"]

                    pil_img = Image.open(io.BytesIO(img_bytes_raw))

                    # Skip tiny images
                    if pil_img.width < 100 or pil_img.height < 100:
                        continue

                    # Deduplicate by (width, height, byte_length)
                    dedup_key = (pil_img.width, pil_img.height, len(img_bytes_raw))
                    if dedup_key in seen_sizes:
                        continue
                    seen_sizes.add(dedup_key)

                    if pil_img.mode not in ("RGB", "RGBA", "L"):
                        pil_img = pil_img.convert("RGB")

                    png_buffer = io.BytesIO()
                    pil_img.save(png_buffer, format="PNG")
                    png_bytes = png_buffer.getvalue()

                    images.append({
                        "image_bytes": png_bytes,
                        "page_num": page_num,
                        "index": img_counter,
                        "source": source_label,
                        "label": f"{source_label} – Page {page_num + 1}, Img {img_index + 1}",
                        "width": pil_img.width,
                        "height": pil_img.height,
                    })
                    img_counter += 1

                except Exception:
                    continue

        doc.close()
        logger.info(f"Smart-extracted {len(images)} unique images from {source_label} PDF")

    except Exception as e:
        logger.error(f"Smart extraction failed: {e}")

    return images
