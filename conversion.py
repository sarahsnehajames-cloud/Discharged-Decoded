import json
import os


def _fallback(info: dict) -> str:
    sections = []
    for med in info.get("medications", []):
        name = med.get("medication") or "Medication"
        details = []
        if med.get("dosage"): details.append(med["dosage"])
        if med.get("frequency"): details.append(med["frequency"])
        if med.get("duration"): details.append(med["duration"])
        sentence = f"**{name}:** " + ", ".join(details) if details else f"**{name}:** Follow the instructions shown in your discharge document."
        if med.get("instructions"): sentence += f"\n\n{med['instructions']}"
        sections.append(sentence)
    if info.get("condition_or_procedure"):
        sections.insert(0, f"**Your condition/procedure:** {info['condition_or_procedure']}")
    if info.get("other_instructions"):
        sections.append(f"**Other instructions:**\n{info['other_instructions']}")
    return "\n\n".join(sections) or "No confirmed information was available."


def plain_language_conversion(info: dict) -> str:
    if not os.getenv("OPENAI_API_KEY"):
        return _fallback(info)

    try:
        from openai import OpenAI
        client = OpenAI()
        prompt = """Rewrite the following CONFIRMED discharge information into plain, easy-to-understand language for a patient.
Rules:
- Do not add medical facts, warnings, diagnoses, doses, or instructions that are not present.
- Do not change medication dose, frequency, duration, or timing.
- Keep uncertainty explicit.
- Use short sentences and bullets.
- Preserve clinically important wording where necessary.
- Do not provide a new diagnosis or personalised medical advice.
Return Markdown only.

CONFIRMED INFORMATION:
""" + json.dumps(info, ensure_ascii=False)
        response = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
            input=prompt,
        )
        return response.output_text.strip()
    except Exception:
        return _fallback(info)
