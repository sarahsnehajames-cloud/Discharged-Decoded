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
            pix = page.get_pixmap(
                matrix=fitz.Matrix(2, 2),
                alpha=False,
            )
            image = Image.open(io.BytesIO(pix.tobytes("png")))
            ocr_pages.append(pytesseract.image_to_string(image))

        return "\n".join(ocr_pages).strip()
    except Exception:
        return ""

def _docx_text(data: bytes) -> str:
    from docx import Document

    document = Document(io.BytesIO(data))
    parts = [
        p.text for p in document.paragraphs
        if p.text.strip()
    ]

    for table in document.tables:
        for row in table.rows:
            parts.append(
                " | ".join(cell.text.strip() for cell in row.cells)
            )

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
    if extension in {
        ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"
    }:
        return _image_text(data)

    raise ValueError("Unsupported file type")


def _heuristic_extract(text: str) -> dict:
    """Extract medication details and discharge instructions."""
    lines = [
        line.strip(" •\t-")
        for line in text.splitlines()
        if line.strip()
    ]

    meds = []
    current_med = None
    wound_care= {
        "frequency": "",
        "duration": "",
        "instructions": [],
    }
    other_instructions = []
    condition = ""

    def save_medication():
        if current_med is not None:
            meds.append(current_med.copy())

    for line in lines:
        # Start a new medication section.
        med_match = re.match(
            r"^Medication\s*\d+\s*:\s*(.+)$",
            line,
            re.I,
        )

        if med_match:
            save_medication()
            current_med = {
                "medication": med_match.group(1).strip(),
                "dosage": "",
                "frequency": "",
                "duration": "",
                "instructions": "",
            }
            continue

        # Read labelled medication fields.
        field_match = re.match(
            r"^(Dose|Dosage|Frequency|Duration|Instructions?)\s*:\s*(.*)$",
            line,
            re.I,
        )

        if field_match and current_med is not None:
            field = field_match.group(1).lower()
            value = field_match.group(2).strip()

            if field in {"dose", "dosage"}:
                current_med["dosage"] = value
            elif field == "frequency":
                current_med["frequency"] = value
            elif field == "duration":
                current_med["duration"] = value
            else:
                current_med["instructions"] = value

            continue

        # Support medication details written on one line.
        dose_match = re.search(
            r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|mL|units?|%)\b",
            line,
            re.I,
        )

        if dose_match and current_med is None:
            name = re.sub(
                r"^(?:Medication|Medicine)\s*\d+\s*:\s*",
                "",
                line[:dose_match.start()],
                flags=re.I,
            ).strip(" :-")

            if name:
                current_med = {
                    "medication": name,
                    "dosage": dose_match.group(0),
                    "frequency": "",
                    "duration": "",
                    "instructions": "",
                }

        elif current_med is not None:
            if re.match(r"^Frequency\s*:", line, re.I):
                current_med["frequency"] = re.sub(
                    r"^Frequency\s*:\s*", "", line, flags=re.I
                )
            elif re.match(r"^Duration\s*:", line, re.I):
                current_med["duration"] = re.sub(
                    r"^Duration\s*:\s*", "", line, flags=re.I
                )
            elif re.match(r"^Instructions?\s*:", line, re.I):
                current_med["instructions"] = re.sub(
                    r"^Instructions?\s*:\s*", "", line, flags=re.I
                )
        
        
        # Extract wound-care details.
        if re.search(
            r"\b(dressing|dressings|wound|wounds|bandage|gauze)\b",
            line,
            re.I,
        ):
            if not any(
                line.casefold() == saved.casefold()
                for saved in wound_care["instructions"]
            ):
                wound_care["instructions"].append(line)

            frequency = re.search(
                r"\b(?:every|each)\s+\d+\s+"
                r"(?:hours?|days?|weeks?|months?)\b",
                line,
                re.I,
            )
            duration = re.search(
                r"\bfor\s+(\d+\s+"
                r"(?:hours?|days?|weeks?|months?))\b",
                line,
                re.I,
            )

            if frequency:
                wound_care["frequency"] = frequency.group(0)

            if duration:
                wound_care["duration"] = duration.group(1)


        
        if re.search(
            r"\b(diagnosis|diagnosed with|condition|procedure|"
            r"admitted for|reason for admission)\b",
            line,
            re.I,
        ):
            condition = re.sub(
                r"^.*?:\s*", "", line
            ).strip()

        # Capture ordinary care instructions.
        if re.match(
            r"^(additional instructions|other instructions|"
            r"drink\b|contact\b|follow\b|change\b|keep\b)",
            line,
            re.I,
        ):
            if line not in other_instructions:
                other_instructions.append(line)

    save_medication()

    return {
    "medications": meds,
    "condition_or_procedure": condition,
    "other_instructions": "\n".join(other_instructions),
    "wound_care": wound_care,
}


def _openai_extract(text: str) -> dict:
    from openai import OpenAI

    client = OpenAI()

    prompt = """Extract structured information from this discharge document.
Return ONLY valid JSON with this exact shape:

{"medications":[{"medication":"","dosage":"","frequency":"","duration":"","instructions":""}],"condition_or_procedure":"","other_instructions":"","wound_care":{"frequency":"","duration":"","instructions":[]}}

Do not invent missing information.
Preserve medication doses, frequencies and durations exactly.
Include EVERY line mentioning a wound or dressing in wound_care.instructions.
Preserve the original wording and all numbers or time periods in those lines.
Extract frequency and duration into wound_care.frequency and wound_care.duration when stated.
Do not replace specific wound-care instructions with generic advice.

DOCUMENT TEXT:
""" + text

    response = client.responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
        input=prompt,
    )

    return json.loads(response.output_text.strip())


def extract_information(text: str) -> dict:
    """Extract information and preserve wound-care details from source text."""
    result = None

    if os.getenv("OPENAI_API_KEY"):
        try:
            result = _openai_extract(text)
        except Exception:
            result = None

    if not isinstance(result, dict):
        result = _heuristic_extract(text)

    if not isinstance(result.get("medications"), list):
        result["medications"] = []

    
    # Ensure wound care uses the same structure for AI and fallback.
    heuristic_result = _heuristic_extract(text)
    result["wound_care"] = heuristic_result["wound_care"]
    print("EXTRACTED SOURCE TEXT:", repr(text))
    print("WOUND CARE RESULT:", heuristic_result["wound_care"])
    result.setdefault("condition_or_procedure", "")
    result.setdefault("other_instructions", "")
    return result
