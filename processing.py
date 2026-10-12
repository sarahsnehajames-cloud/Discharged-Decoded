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
    """Extract medication details from labelled discharge text."""
    lines = [
        line.strip(" •\t-")
        for line in text.splitlines()
        if line.strip()
    ]

    meds = []
    current_med = None
    other_instructions = []
    condition = ""

    def save_medication():
        if current_med is not None:
            meds.append(current_med.copy())

    for line in lines:
        # Start a new medication section.
        med_match = re.match(
            r"^Medication\s*\d*\s*:\s*(.+)$",
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

        # Read labelled fields such as Dose: 500 mg.
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

        # Also support medication details written on one line.
        dose_match = re.search(
            r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|mL|units?|%)\b",
            line,
            re.I,
        )

        if dose_match and current_med is None:
            current_med = {
                "medication": re.sub(
                    r"^(?:Medication|Medicine)\s*\d*\s*:\s*",
                    "",
                    line[:dose_match.start()],
                    flags=re.I,
                ).strip(" :-"),
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

        if re.search(
            r"\b(diagnosis|diagnosed with|condition|procedure|"
            r"admitted for|reason for admission)\b",
            line,
            re.I,
        ):
            condition = re.sub(
                r"^.*?:\s*", "", line
            ).strip()

        if re.match(
            r"^(additional instructions|other instructions|"
            r"drink |contact |follow )",
            line,
            re.I,
        ):
            other_instructions.append(line)

    save_medication()

    return {
        "medications": meds,
        "condition_or_procedure": condition,
        "other_instructions": "\n".join(other_instructions),
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
