import io
import json
import os
import re
from pathlib import Path


def _pdf_text(data: bytes) -> str:
    import fitz
    doc = fitz.open(stream=data, filetype="pdf")
    pages = [page.get_text("text") for page in doc]
    text = "\n".join(pages).strip()
    if text:
        return text

    # OCR fallback for scanned PDFs.
    try:
        import pytesseract
        from PIL import Image
        ocr_pages = []
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            image = Image.open(io.BytesIO(pix.tobytes("png")))
            ocr_pages.append(pytesseract.image_to_string(image))
        return "\n".join(ocr_pages).strip()
    except Exception:
        return ""


def _docx_text(data: bytes) -> str:
    from docx import Document
    document = Document(io.BytesIO(data))
    parts = [p.text for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text.strip() for cell in row.cells))
    return "\n".join(parts).strip()


def _image_text(data: bytes) -> str:
    import pytesseract
    from PIL import Image, ImageOps
    image = Image.open(io.BytesIO(data))
    image = ImageOps.exif_transpose(image).convert("RGB")
    return pytesseract.image_to_string(image).strip()


def extract_text_from_upload(data: bytes, filename: str) -> str:
    extension = Path(filename).suffix.lower()
    if extension == ".pdf":
        return _pdf_text(data)
    if extension == ".docx":
        return _docx_text(data)
    if extension in {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}:
        return _image_text(data)
    raise ValueError("Unsupported file type")


def _heuristic_extract(text: str) -> dict:
    """Fallback extraction for demos/tests when no LLM API key is configured."""
    lines = [line.strip(" •\t") for line in text.splitlines() if line.strip()]
    meds = []
    dose_pattern = re.compile(r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|mL|units?|%)\b", re.I)
    freq_pattern = re.compile(r"\b(?:once|twice|three times|four times|daily|weekly|every\s+\d+\s+hours?|\d+\s*x\s*(?:daily|a day))\b", re.I)
    duration_pattern = re.compile(r"\b(?:for\s+)?\d+\s*(?:days?|weeks?|months?)\b", re.I)

    for line in lines:
        dose = dose_pattern.search(line)
        if not dose:
            continue
        freq = freq_pattern.search(line)
        duration = duration_pattern.search(line)
        name = re.sub(r"^(?:medication|medicine)\s*:\s*", "", line[:dose.start()], flags=re.I).strip(" :-") or line.split()[0]
        meds.append({
            "medication": name,
            "dosage": dose.group(0),
            "frequency": freq.group(0) if freq else "",
            "duration": duration.group(0) if duration else "",
            "instructions": line,
        })

    condition = ""
    for line in lines:
        if re.search(r"\b(diagnosis|diagnosed with|condition|procedure|admitted for|reason for admission)\b", line, re.I):
            condition = re.sub(r"^.*?:", "", line).strip()
            break

    return {
        "medications": meds,
        "condition_or_procedure": condition,
        "other_instructions": "\n".join(lines[:8]) if lines else "",
    }


def _openai_extract(text: str) -> dict:
    from openai import OpenAI
    client = OpenAI()
    prompt = """Extract structured information from this discharge document. Return ONLY valid JSON with this exact shape:
{"medications":[{"medication":"","dosage":"","frequency":"","duration":"","instructions":""}],"condition_or_procedure":"","other_instructions":""}
Do not invent missing information. Preserve uncertainty or unclear wording rather than guessing.

DOCUMENT TEXT:
""" + text
    response = client.responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
        input=prompt,
    )
    raw = response.output_text.strip()
    return json.loads(raw)


def extract_information(text: str) -> dict:
    if os.getenv("OPENAI_API_KEY"):
        try:
            return _openai_extract(text)
        except Exception:
            pass
    return _heuristic_extract(text)
