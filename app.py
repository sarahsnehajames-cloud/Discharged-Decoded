import os
import io
import json
import base64
import tempfile
from pathlib import Path

import streamlit as st

from processing import extract_text_from_upload, extract_information
from conversion import plain_language_conversion
from condition_education import get_nhs_search_url



# Discharged, Decoded — colour theme
st.markdown("""
<style>
/* Main app background */
.stApp {
    background-color: #FFFFFF;
}

/* Main app title and section headings */
h1, h2, h3 {
    color: #7254A5 !important;
}

/* Soft blue brand banner */
.brand-banner {
    background-color: #EAF3FC;
    padding: 24px 28px;
    border-radius: 16px;
    border-left: 6px solid #7254A5;
    margin-bottom: 24px;
}

/* Brand title */
.brand-banner h1 {
    color: #7254A5 !important;
    margin: 0;
    font-size: 2rem;
}

/* Brand subtitle */
.brand-banner p {
    color: #29283A;
    margin: 8px 0 0 0;
    font-size: 1rem;
}

/* Light lavender medication cards */
.st-key-med-card {
    background-color: #F7F8FC;
    border: 1px solid #E4DDF0;
    border-radius: 14px;
    padding: 18px;
    margin: 12px 0;
}

/* Purple buttons */
.stButton > button {
    background-color: #7254A5;
    color: white;
    border: none;
    border-radius: 10px;
}

/* Visible keyboard focus */
.stButton > button:focus-visible {
    outline: 3px solid #29283A;
    outline-offset: 3px;
}
</style>
""", unsafe_allow_html=True)


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

st.markdown("""
<div class="brand-banner">
    <h1>Discharged, Decoded</h1>
    <p>Your discharge information, made clearer.</p>
</div>
""", unsafe_allow_html=True)
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
                    st.text_area("DEBUG: Extracted document text", text, height=300)
                    if not text.strip():
                        st.error("No readable text was found. Try a clearer photo or a higher-quality document.")
                    else:
                        st.session_state.filename = uploaded.name
                        st.session_state.ocr_text = text
                        st.write("DEBUG — raw extracted document text:", text)
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
            st.session_state.plain_language = ""
            st.session_state.confirmed = True
            st.session_state.step = 3
            st.rerun()


elif st.session_state.step == 3:
    st.subheader("Plain-language summary")
    st.success(
        "Information confirmed. Medical details below are based only "
        "on the confirmed fields."
    )

    if not st.session_state.plain_language:
        with st.spinner("Preparing your summary..."):
            try:
                st.write("DEBUG — confirmed information:", st.session_state.extracted)
                st.session_state.plain_language = plain_language_conversion(
                    st.session_state.extracted
                )
            except Exception as exc:
                st.error(f"Plain-language conversion could not run: {exc}")

    
    if st.session_state.plain_language:
        with st.container(border=True):
            st.markdown("## Your discharge summary")
            st.markdown(st.session_state.plain_language)
            st.code(st.session_state.plain_language)
    else:
        st.warning(
            "No summary is available yet. Please review the confirmed information."
        )

    st.warning(
        "This is a plain-language explanation, not a replacement for "
        "the discharge document or advice from a clinician."
    )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("← Edit confirmed information", use_container_width=True):
            st.session_state.step = 2
            st.session_state.plain_language = ""
            st.rerun()

    with c2:
        if st.button(
            "Continue to education →",
            type="primary",
            use_container_width=True,
        ):
            st.session_state.step = 4
            st.rerun()



elif st.session_state.step == 4:
    st.subheader("Condition education")

    condition = (
        st.session_state.extracted.get("condition_or_procedure") or ""
    ).strip()

    if condition:
        st.write(f"General information about: **{condition}**")

        st.info(
            "This section links to general NHS health information. "
            "It does not replace your discharge instructions or "
            "personal advice from your healthcare professional."
        )

        st.link_button(
            "Search NHS information about this condition",
            get_nhs_search_url(condition),
            use_container_width=True,
        )
    else:
        st.warning(
            "No confirmed condition or procedure was found. "
            "Please check the discharge information before searching."
        )

    st.link_button(
        "Browse NHS Health A to Z",
        "https://www.nhs.uk/health-a-to-z/",
    )

    if st.button(
        "Start another document",
        type="primary",
        use_container_width=True,
    ):
        reset()


st.divider()
st.caption("Prototype: always check the original discharge document and follow instructions from your healthcare team.")
