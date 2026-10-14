import json
import os
import re

def simplify_wording(text: str) -> str:
    """Simplify a few familiar phrases without changing the instruction."""
    if not text:
        return ""

    replacements = {
        "orally": "by mouth",
        "twice daily": "two times a day",
        "three times daily": "three times a day",
        "once daily": "once a day",
        "as required": "when needed",
        "as directed": "following the instructions provided",
        "dressing": "dressing (the covering over a wound)",
    }

    result = text

    for original, simpler in replacements.items():
        import re
        result = re.sub(
            rf"\b{re.escape(original)}\b",
            simpler,
            result,
            flags=re.IGNORECASE,
        )

    return result


def _fallback(info: dict) -> str:
    """Show confirmed information in clear sections."""
    sections = []

    condition = (info.get("condition_or_procedure") or "").strip()
    if condition:
        sections.append(
            f"### Your condition or procedure\n\n"
            f"{simplify_wording(condition)}"
        )

    for med in info.get("medications", []):
        name = med.get("medication") or "Medication"
        details = []

        fields = [
            ("Dose", med.get("dosage")),
            ("How often", med.get("frequency")),
            ("How long", med.get("duration")),
            ("Instructions", med.get("instructions")),
        ]

        for label, value in fields:
            if value and str(value).strip():
                details.append(
                    f"**{label}:** "
                    f"{simplify_wording(str(value).strip())}"
                )

        if not details:
            details.append(
                "Please check your discharge document for instructions."
            )

        sections.append(f"### {name}\n\n" + "\n\n".join(details))

    other = (info.get("other_instructions") or "").strip()

    if other:
        dressing_lines = []
        other_lines = []

        
        for line in re.split(
            r"(?<=[.!?])\s+|\n+",
            other,
        ):

            line = line.strip()
            if not line:
                continue

            if re.search(r"dress|wound", line, re.IGNORECASE):
                dressing_lines.append(line)
            else:
                other_lines.append(line)

        if dressing_lines:
            original = "\n".join(dressing_lines)
            dressing_section = ["### Dressing care"]
            seen_duration = False

            
            frequencies = re.findall(
                r"\b(?:every|each)\s+\d+\s+"
                r"(?:days?|weeks?|months?|hours?)\b",
                original,
                re.IGNORECASE,
            )

            durations = re.findall(
                r"\bfor\s+\d+\s+"
                r"(?:days?|weeks?|months?|hours?)\b",
                original,
                re.IGNORECASE,
            )

            if frequencies:
                dressing_section.append(
                    "**Frequency:** "
                    + ", ".join(dict.fromkeys(frequencies))
                )


            if durations and not seen_duration:
                dressing_section.append(
                    "**How long:** " + ", ".join(dict.fromkeys(durations))
            )
            seen_duration = True

            instructions = [
                line.strip()
                for line in dressing_lines
                if line.strip()
            ]

            dressing_section.append(
                "**Instructions:**\n\n"
                + "\n".join(
                    f"- {simplify_wording(line)}"
                    for line in instructions
                )
            )  

            sections.append("\n\n".join(dressing_section))

        if other_lines:
            sections.append(
                "### Other discharge instructions\n\n"
                + simplify_wording("\n".join(other_lines))
            )

    return "\n\n---\n\n".join(sections) or (
        "No confirmed discharge information was available."
    )

def plain_language_conversion(info: dict) -> str:
    """Simplify confirmed discharge information, with a no-AI fallback."""
    if not os.getenv("OPENAI_API_KEY"):
        return _fallback(info)

    try:
        from openai import OpenAI

        client = OpenAI()

        prompt = """Make the confirmed discharge information easier for a
patient to understand.

Rules:
- Keep each medication in its own section.
- Show the medication name, dose, frequency, duration and special
  instructions when provided.
- Explain complicated wording in everyday English.
- Explain care instructions, such as dressing changes, only using
  information supported by the supplied text.
- Do not guess whether a medicine is a tablet, liquid or injection.
- Do not invent missing dates, doses, timings, durations or instructions.
- Do not change the meaning of any clinical instruction.
- Clearly flag information that is missing or unclear.
- Do not explain what each medication is used for; that belongs in
  the separate education section.
- Use short sentences and clear headings.
- Return Markdown only.

CONFIRMED DISCHARGE INFORMATION:
""" + json.dumps(info, ensure_ascii=False)

        response = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
            input=prompt,
        )

        result = response.output_text.strip()

        
        # Remove the original wording section.
        result = re.split(
            r"(?i)original discharge wording\s*:?",
            result,
            maxsplit=1,
        )[0].strip()

        # Remove every repeated How long line, keeping the first.
        lines = result.splitlines()
        cleaned = []
        seen_duration = False

        for line in lines:
            if re.search(r"how long\s*:", line, re.IGNORECASE):
                if seen_duration:
                    continue
                seen_duration = True
            cleaned.append(line)

        result = "\n".join(cleaned).strip()


        return result if result else _fallback(info)

    except Exception:
        return _fallback(info)
