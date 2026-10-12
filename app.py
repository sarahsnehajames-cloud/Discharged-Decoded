import os
import io
import json
import base64
import tempfile
from pathlib import Path

import streamlit as st

from processing import extract_text_from_upload, extract_information
from conversion import plain_language_conversion

st.set_page_config(page_title="Discharged, Decoded", page_icon="💊", layout="centered")

LANGUAGES = {
    "English": "en",
    "Español": "es",
    "Français": "fr",
    "中文": "zh",
    "العربية": "ar",
}


def init_state():
    defaults = {
        "step": 1,
        "filename": None,
        "ocr_text": "",
        "extracted": {},
        "confirmed": False,
        "plain_language": "",
        "language": "English",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset():
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()


init_state()

# Header
st.title("Discharged, Decoded")
st.caption("Turn discharge paperwork into information that is easier to understand.")

# UI language only. Medical content is deliberately not translated here.
st.session_state.language = st.selectbox(
    "Language",
    list(LANGUAGES.keys()),
    index=list(LANGUAGES.keys()).index(st.session_state.language),
    help="This changes the app interface. It does not automatically translate the medical instructions.",
)

st.progress(st.session_state.step / 4)
st.caption(f"Step {st.session_state.step} of 4")

if st.session_state.step == 1:
    st.subheader("Upload discharge")
    st.write("Upload a PDF, Word document, or image of your discharge paperwork.")

    uploaded = st.file_uploader(
        "Upload Photo / PDF",
        type=["pdf", "docx", "png", "jpg", "jpeg", "webp", "tif", "tiff"],
        accept_multiple_files=False,
    )

    if uploaded:
        st.success(f"Selected: {uploaded.name}")
        if st.button("Process document", type="primary", use_container_width=True):
            with st.spinner("Reading your document..."):
                try:
                    raw = uploaded.getvalue()
                    text = extract_text_from_upload(raw, uploaded.name)
                    if not text.strip():
                        st.error("No readable text was found. Try a clearer photo or a higher-quality document.")
                    else:
                        st.session_state.filename = uploaded.name
                        st.session_state.ocr_text = text
                        st.session_state.extracted = extract_information(text)
                        st.session_state.confirmed = False
                        st.session_state.step = 2
                        st.rerun()
                except Exception as exc:
                    st.error(f"The document could not be processed: {exc}")

    st.divider()
    st.info("For photographs, use good lighting and keep the page flat and in focus.")

elif st.session_state.step == 2:
    st.subheader("Review extracted information")
    st.caption(f"Source: {st.session_state.filename}")

    extracted = st.session_state.extracted
    medications = extracted.get("medications", []) or [{}]

    st.markdown("### Medication")
    edited_meds = []
    for i, med in enumerate(medications):
        with st.container(border=True):
            name = st.text_input("Medication", med.get("medication", ""), key=f"med_name_{i}")
            dosage = st.text_input("Dosage", med.get("dosage", ""), key=f"med_dose_{i}")
            frequency = st.text_input("Frequency", med.get("frequency", ""), key=f"med_freq_{i}")
            duration = st.text_input("Duration", med.get("duration", ""), key=f"med_duration_{i}")
            instructions = st.text_area("Instructions", med.get("instructions", ""), key=f"med_inst_{i}")
            edited_meds.append({
                "medication": name,
                "dosage": dosage,
                "frequency": frequency,
                "duration": duration,
                "instructions": instructions,
            })

    condition = st.text_input("Condition / procedure", extracted.get("condition_or_procedure", ""))
    other_instructions = st.text_area("Other instructions", extracted.get("other_instructions", ""))

    with st.expander("View OCR text"):
        st.text_area("Extracted text", st.session_state.ocr_text, height=250, disabled=True)

    c1, c2 = st.columns(2)
    with c1:
        if st.button("← Re-upload", use_container_width=True):
            st.session_state.step = 1
            st.rerun()
    with c2:
        if st.button("Confirm information", type="primary", use_container_width=True):
            st.session_state.extracted = {
                "medications": edited_meds,
                "condition_or_procedure": condition,
                "other_instructions": other_instructions,
            }
            st.session_state.confirmed = True
            st.session_state.step = 3
            st.rerun()

elif st.session_state.step == 3:
    st.subheader("Plain-language summary")
    st.success("Information confirmed. Medical details below are based only on the confirmed fields.")

    if not st.session_state.plain_language:
        with st.spinner("Converting the confirmed information into clearer language..."):
            try:
                st.session_state.plain_language = plain_language_conversion(st.session_state.extracted)
            except Exception as exc:
                st.session_state.plain_language = ""
                st.error(f"Plain-language conversion could not run: {exc}")

    if st.session_state.plain_language:
        st.markdown(st.session_state.plain_language)
    else:
        st.warning("No conversion is available yet. Check that an AI provider is configured.")

    st.warning("This is a plain-language explanation, not a replacement for the discharge document or advice from a clinician.")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("← Edit confirmed information", use_container_width=True):
            st.session_state.step = 2
            st.session_state.plain_language = ""
            st.rerun()
    with c2:
        if st.button("Continue to education →", type="primary", use_container_width=True):
            st.session_state.step = 4
            st.rerun()

elif st.session_state.step == 4:
    st.subheader("Condition education")
    condition = st.session_state.extracted.get("condition_or_procedure", "the condition or procedure")
    st.write(f"General information about: **{condition}**")
    st.info("Condition education is a separate module. It should use the confirmed condition/procedure and clearly distinguish general information from patient-specific medical advice.")
    st.write("The confirmed information and plain-language summary are ready for the next team module.")

    if st.button("Start another document", type="primary", use_container_width=True):
        reset()

st.divider()
st.caption("Prototype: always check the original discharge document and follow instructions from your healthcare team.")
