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
from datetime import date, timedelta
from pharmacy import find_pharmacies



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


UI_TEXT = {
    "English": {
        "tagline": "Your discharge information, made clearer.",
        "caption": "Turn discharge paperwork into information that is easier to understand.",
        "language": "Language",
        "upload": "Upload discharge",
        "review": "Review extracted information",
        "summary": "Plain-language summary",
        "education": "Condition education",
        "process": "Process document",
        "confirm": "Confirm information",
        "edit": "← Edit confirmed information",
        "continue": "Continue to education →",
        "start_again": "Start another document",
        "reupload": "← Re-upload",
    },
    "Español": {
        "tagline": "La información de alta médica, más clara.",
        "caption": "Convierte los documentos de alta en información más fácil de entender.",
        "language": "Idioma",
        "upload": "Subir documento de alta",
        "review": "Revisar la información extraída",
        "summary": "Resumen en lenguaje sencillo",
        "education": "Información sobre la enfermedad",
        "process": "Procesar documento",
        "confirm": "Confirmar información",
        "edit": "← Editar información confirmada",
        "continue": "Continuar a la información →",
        "start_again": "Empezar otro documento",
        "reupload": "← Volver a subir",
    },
    "Français": {
        "tagline": "Vos informations de sortie, plus faciles à comprendre.",
        "caption": "Rendez les documents de sortie plus faciles à comprendre.",
        "language": "Langue",
        "upload": "Importer le document de sortie",
        "review": "Vérifier les informations extraites",
        "summary": "Résumé en langage simple",
        "education": "Informations sur la maladie",
        "process": "Traiter le document",
        "confirm": "Confirmer les informations",
        "edit": "← Modifier les informations confirmées",
        "continue": "Continuer vers les informations →",
        "start_again": "Commencer un autre document",
        "reupload": "Importer à nouveau",
    },
    "中文": {
        "tagline": "让您的出院信息更清晰易懂。",
        "caption": "将出院文件转换为更容易理解的信息。",
        "language": "语言",
        "upload": "上传出院文件",
        "review": "检查提取的信息",
        "summary": "通俗易懂的摘要",
        "education": "疾病信息",
        "process": "处理文件",
        "confirm": "确认信息",
        "edit": "← 编辑已确认的信息",
        "continue": "继续查看健康信息 →",
        "start_again": "开始处理另一份文件",
        "reupload": "重新上传",
    },
    "العربية": {
        "tagline": "معلومات خروجك من المستشفى بشكل أوضح.",
        "caption": "حوّل مستندات الخروج إلى معلومات أسهل للفهم.",
        "language": "اللغة",
        "upload": "تحميل مستند الخروج",
        "review": "مراجعة المعلومات المستخرجة",
        "summary": "ملخص بلغة بسيطة",
        "education": "معلومات عن الحالة الصحية",
        "process": "معالجة المستند",
        "confirm": "تأكيد المعلومات",
        "edit": "← تعديل المعلومات المؤكدة",
        "continue": "المتابعة إلى التثقيف الصحي →",
        "start_again": "البدء بمستند آخر",
        "reupload": "إعادة التحميل",
    },
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
        "medication_schedule": [],
        "schedule_created": False,
        "reminders_active": False,
        "selected_calendar_date": None,
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

ui = UI_TEXT[st.session_state.language]


st.progress(st.session_state.step / 6)
st.caption(f"Step {st.session_state.step} of 6")

if st.session_state.step != 1:
    if st.button(":material/home: Home", key="global_home"):
        st.session_state.step = 1
        st.rerun()

if st.session_state.step == 1:
    st.subheader(":material/home: Home")

    if st.button("📅 View medication schedule", use_container_width=True):
        st.session_state.step = 4
        st.rerun()

    st.divider()

    st.subheader("💊 Today's medication")
    schedule = st.session_state.get("medication_schedule", [])
    today = date.today()

    todays_meds = [
        item for item in schedule
        if item["start"] <= today <= item["end"]
    ]

    if todays_meds:
        for item in todays_meds:
            st.write(
                f"**{item['medication']}** — "
                f"{item['dosage']} · {item['frequency']}"
            )
    else:
        st.info("No medication scheduled for today yet.")

    st.divider()

    st.subheader(ui["upload"])

    st.write("Upload a PDF, Word document, or image of your discharge paperwork.")

    uploaded = st.file_uploader(
        "Upload Photo / PDF",
        type=["pdf", "docx", "png", "jpg", "jpeg", "webp", "tif", "tiff"],
        accept_multiple_files=False,
    )

    if uploaded:
        st.success(f"Selected: {uploaded.name}")
        if st.button(ui["process"], type="primary", use_container_width=True):
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
    st.subheader(ui["review"])
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
        if st.button(ui["reupload"], use_container_width=True):
            st.session_state.step = 1
            st.rerun()
    with c2:
        if st.button(ui["confirm"], type="primary", use_container_width=True):
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
    st.subheader(ui["summary"])
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
        if st.button(ui["edit"], use_container_width=True):
            st.session_state.step = 2
            st.session_state.plain_language = ""
            st.rerun()

    with c2:
        if st.button(
            "Continue to medication calendar →",
            type="primary",
            use_container_width=True,
        ):
            st.session_state.step = 4
            st.rerun()

elif st.session_state.step == 4:
    import calendar

    st.subheader("My medication calendar")

    if st.button(":material/home: Back to Home", key="calendar_home"):
        st.session_state.step = 1
        st.rerun()

    st.write(
        "Review the start date and duration for each medicine "
        "before creating your schedule."
    )

    start_date = st.date_input(
        "When did you start, or will you start, your medication?",
        value=date.today(),
        key="calendar_start_date",
    )

    medications = st.session_state.extracted.get("medications", [])

    if not medications:
        st.warning("No confirmed medications were found.")
    else:
        confirmed_schedule = []

        for i, med in enumerate(medications):
            st.markdown(
                f"### {med.get('medication') or f'Medicine {i + 1}'}"
            )
            st.write(
                f"Prescribed dose: {med.get('dosage') or 'Not specified'}"
            )
            st.write(
                f"Frequency: {med.get('frequency') or 'Not specified'}"
            )

            duration_days = st.number_input(
                f"Confirm duration in days for medicine {i + 1}",
                min_value=1,
                max_value=365,
                value=1,
                key=f"calendar_duration_{i}",
                help="Enter the duration stated on your prescription.",
            )

            confirmed_schedule.append({
                "medication": med.get("medication") or f"Medicine {i + 1}",
                "dosage": med.get("dosage") or "Not specified",
                "frequency": med.get("frequency") or "Not specified",
                "start": start_date,
                "end": start_date + timedelta(days=int(duration_days) - 1),
            })

        if st.button("Create my schedule", type="primary"):
            st.session_state.medication_schedule = confirmed_schedule
            st.session_state.schedule_created = True
            st.rerun()

    if st.session_state.get("schedule_created"):
        schedule = st.session_state.medication_schedule
        today = date.today()
        year = today.year
        month = today.month

        st.markdown("## My medication calendar")
        st.subheader(f"{calendar.month_name[month]} {year}")

        weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        cols = st.columns(7)

        for col, weekday in zip(cols, weekdays):
            col.markdown(f"**{weekday}**")

        if st.session_state.selected_calendar_date is None:
            st.session_state.selected_calendar_date = today

        for week in calendar.monthcalendar(year, month):
            cols = st.columns(7)

            for col, day_num in zip(cols, week):
                with col:
                    if day_num == 0:
                        st.write(" ")
                    else:
                        current_date = date(year, month, day_num)

                        if st.button(
                            str(day_num),
                            key=f"calendar_day_{year}_{month}_{day_num}",
                            use_container_width=True,
                        ):
                            st.session_state.selected_calendar_date = current_date
                            st.rerun()

                        for item in schedule:
                            if item["start"] <= current_date <= item["end"]:
                                st.caption(f"💊 {item['medication']}")

        selected_date = st.session_state.selected_calendar_date

        st.markdown(
            f"### Medication for {selected_date.strftime('%A, %d %B %Y')}"
        )

        found_medication = False

        for item in schedule:
            if item["start"] <= selected_date <= item["end"]:
                found_medication = True
                st.markdown(f"**{item['medication']}**")
                st.write(f"Prescribed dose: {item['dosage']}")
                st.write(f"Frequency: {item['frequency']}")

        if not found_medication:
            st.info("No medication course is scheduled for this date.")

        st.caption(
            "Dates are based on the start dates and durations you confirmed."
        )

        
        st.divider()
        st.subheader("Confirm your reminder schedule")

        st.write(
            "Review your medication details and dates against "
            "your prescription before activating reminders."
        )

        if st.button(
            "Activate reminders",
            type="primary",
            use_container_width=True,
            key="activate_reminders",
        ):
            st.session_state.reminders_active = True
            st.success("Your reminder schedule has been activated in this app.")
            st.rerun()

        if st.session_state.get("reminders_active", False):
            st.success("Reminders are marked as active.")

            st.caption(
                "This prototype does not yet send notifications "
                "when the app is closed."
            )


        if st.button("Continue to condition education →", type="primary"):
            st.session_state.step = 5
            st.rerun()


elif st.session_state.step == 5:
    st.subheader(ui["education"])

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
        "Find a pharmacy →",
        type="primary",
        use_container_width=True,
    ):
        st.session_state.step = 6
        st.rerun()


    if st.button(
        "Start another document",
        type="primary",
        use_container_width=True,
    ):
        reset()


elif st.session_state.step == 6:
    st.subheader("Find a nearby pharmacy")

    st.write(
        "Enter a postcode or town to find pharmacies "
        "and get directions."
    )

    pharmacy_location = st.text_input(
        "Postcode or town",
        placeholder="e.g. L1 1JQ or Liverpool",
        key="pharmacy_location",
    )

    
    if st.button("Find pharmacies", type="primary"):
        location = pharmacy_location.strip()

        if not location:
            st.warning("Please enter a postcode or town.")
        else:
            with st.spinner("Searching for nearby pharmacies..."):
                pharmacies = find_pharmacies(location)

            if pharmacies is None:
                st.error(
                    "The pharmacy search is temporarily unavailable. "
                    "Please try again later."
                )
            elif not pharmacies:
                st.info(
                    "No pharmacies were found nearby. "
                    "Try a nearby town or a different postcode."
                )
            else:
                st.success(f"Found {len(pharmacies)} pharmacies.")

                for i, pharmacy in enumerate(pharmacies):
                    with st.container(border=True):
                        st.subheader(pharmacy["name"])
                        st.write(pharmacy["address"])
                        st.link_button(
                            "Get directions",
                            pharmacy["directions"],
                            key=f"pharmacy_directions_{i}",
                        )

    st.caption(
                "Pharmacy information comes from OpenStreetMap "
                "and may be incomplete. Please check details "
                "before travelling."
            )
    st.caption("Map data © OpenStreetMap contributors.")


    if st.button("← Back to condition education"):
        st.session_state.step = 5
        st.rerun()

    if st.button("Start another document"):
        reset()


st.divider()
st.caption("Prototype: always check the original discharge document and follow instructions from your healthcare team.")
