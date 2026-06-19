"""
app.py
DDR Generator — Streamlit UI
Upload Inspection PDF + Thermal PDF → Gemini 2.5 Flash → Download DDR PDF
"""

import streamlit as st
import logging
import time
from datetime import datetime

from utils import setup_logging, get_api_key, format_file_size
from extractor import extract_images_smart, get_pdf_page_count
from generator import generate_ddr
from pdf_builder import build_ddr_pdf

setup_logging()
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="DDR Generator",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        padding: 2rem; border-radius: 12px; margin-bottom: 1.5rem; text-align: center;
    }
    .main-header h1 { color: white; margin: 0; font-size: 2rem; }
    .main-header p  { color: #aaaacc; margin: 0.4rem 0 0 0; font-size: 1rem; }
    .metric-box {
        background: white; border: 1px solid #e0e0e0;
        border-radius: 8px; padding: 1rem; text-align: center;
    }
    .metric-box .val { font-size: 1.8rem; font-weight: bold; color: #16213e; }
    .metric-box .lbl { font-size: 0.8rem; color: #666; margin-top: 4px; }
    .success-box {
        background: #e8f5e9; border: 1px solid #4caf50;
        border-radius: 8px; padding: 1rem 1.2rem; margin-top: 1rem;
    }
    .warning-box {
        background: #fff8e1; border: 1px solid #ffc107;
        border-radius: 8px; padding: 1rem 1.2rem; margin-top: 0.5rem;
    }
    section[data-testid="stSidebar"] { display: none; }
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="main-header">
    <h1>Detailed Diagnostic Report Generator</h1>
    <p>Upload inspection and thermal reports — AI analyzes both — Download structured DDR</p>
</div>
""", unsafe_allow_html=True)

# ── File Uploaders ────────────────────────────────────────────────────────────
col1, col2 = st.columns(2)

with col1:
    st.markdown("#### Inspection Report")
    st.caption("Visual site inspection document (observations, checklists, photos)")
    inspection_file = st.file_uploader(
        "Upload Inspection PDF", type=["pdf"], key="inspection_pdf", label_visibility="collapsed"
    )
    if inspection_file:
        insp_bytes = inspection_file.read()
        st.success(f"**{inspection_file.name}** — {get_pdf_page_count(insp_bytes)} pages, {format_file_size(len(insp_bytes))}")

with col2:
    st.markdown("#### Thermal Images Report")
    st.caption("IR thermography document with temperature readings")
    thermal_file = st.file_uploader(
        "Upload Thermal PDF", type=["pdf"], key="thermal_pdf", label_visibility="collapsed"
    )
    if thermal_file:
        therm_bytes = thermal_file.read()
        st.success(f"**{thermal_file.name}** — {get_pdf_page_count(therm_bytes)} pages, {format_file_size(len(therm_bytes))}")

st.markdown("---")

property_name = st.text_input(
    "Property / Project Name (for filename)", value="Property",
    placeholder="e.g., Flat-8-63-Yamuna-CHS",
)

col_btn, _ = st.columns([1, 3])
with col_btn:
    generate_clicked = st.button(
        "Generate DDR", type="primary", use_container_width=True,
        disabled=not (inspection_file and thermal_file),
    )

if not inspection_file or not thermal_file:
    st.markdown(
        '<div class="warning-box">Please upload both PDFs to enable generation.</div>',
        unsafe_allow_html=True
    )

# ── Generation Flow ───────────────────────────────────────────────────────────
if generate_clicked and inspection_file and thermal_file:

    try:
        resolved_key = get_api_key()
    except ValueError as e:
        st.error(str(e))
        st.stop()

    inspection_file.seek(0)
    thermal_file.seek(0)
    insp_bytes = inspection_file.read()
    therm_bytes = thermal_file.read()

    progress_bar = st.progress(0)
    status_text  = st.empty()

    try:
        # Step 1: Extract images
        status_text.markdown("**Step 1/4** — Extracting images from PDFs...")
        progress_bar.progress(10)

        with st.spinner("Extracting images from Inspection PDF..."):
            inspection_images = extract_images_smart(insp_bytes, "Inspection", max_images=50)
        with st.spinner("Extracting images from Thermal PDF..."):
            thermal_images = extract_images_smart(therm_bytes, "Thermal", max_images=50)

        total_imgs = len(inspection_images) + len(thermal_images)
        progress_bar.progress(25)
        status_text.markdown(
            f"**Step 1/4** — Extracted **{len(inspection_images)}** inspection + "
            f"**{len(thermal_images)}** thermal images"
        )

        # Step 2: Gemini analysis
        status_text.markdown("**Step 2/4** — Uploading PDFs to Gemini 2.5 Flash...")
        progress_bar.progress(35)

        t_start = time.time()
        with st.spinner("Gemini 2.5 Flash is analyzing both documents... This may take 30–90 seconds."):
            ddr_data = generate_ddr(
                api_key=resolved_key,
                inspection_pdf_bytes=insp_bytes,
                thermal_pdf_bytes=therm_bytes,
                property_name=property_name,
            )
        t_elapsed = time.time() - t_start
        progress_bar.progress(70)
        status_text.markdown(f"**Step 2/4** — DDR analysis complete in **{t_elapsed:.1f}s**")

        # Step 3: Build PDF
        status_text.markdown("**Step 3/4** — Assembling DDR PDF with images...")
        progress_bar.progress(80)
        with st.spinner("Building PDF report..."):
            pdf_bytes = build_ddr_pdf(ddr_data, inspection_images, thermal_images, property_name)

        progress_bar.progress(100)
        status_text.markdown("**Step 4/4** — Report ready for download!")

        # ── Results ───────────────────────────────────────────────────────────
        st.markdown("---")
        st.markdown('<div class="success-box"><b>DDR Generated Successfully</b></div>', unsafe_allow_html=True)
        st.markdown(" ")

        summary = ddr_data.get("property_issue_summary", {})
        areas   = ddr_data.get("area_wise_observations", [])
        actions = ddr_data.get("recommended_actions", [])

        m1, m2, m3, m4, m5 = st.columns(5)
        for col, val, lbl in [
            (m1, summary.get("total_issues_found", "N/A"), "Total Issues"),
            (m2, len(areas),    "Areas Inspected"),
            (m3, len(actions),  "Actions Recommended"),
            (m4, total_imgs,    "Images Embedded"),
            (m5, f"{len(pdf_bytes)//1024} KB", "PDF Size"),
        ]:
            with col:
                st.markdown(
                    f'<div class="metric-box"><div class="val">{val}</div><div class="lbl">{lbl}</div></div>',
                    unsafe_allow_html=True
                )

        st.markdown(" ")

        critical = summary.get("critical_issues", [])
        if critical:
            with st.expander(f"{len(critical)} Critical Issue(s) Found", expanded=True):
                for c in critical:
                    st.markdown(f"- {c}")

        filename = f"DDR_{property_name.replace(' ','_')}_{datetime.today().strftime('%Y%m%d')}.pdf"
        st.download_button(
            label="Download DDR PDF",
            data=pdf_bytes,
            file_name=filename,
            mime="application/pdf",
        )

        with st.expander("Raw DDR JSON", expanded=False):
            st.json(ddr_data)

        with st.expander("Area-wise Summary", expanded=False):
            for i, obs in enumerate(areas, 1):
                st.markdown(f"**{i}. {obs.get('area_name','Area')}**")
                st.markdown(f"- Problem: {obs.get('negative_side','N/A')}")
                st.markdown(f"- Source: {obs.get('positive_side','N/A')}")
                therm = obs.get("thermal_reading", "")
                if therm and therm != "Not Available":
                    st.markdown(f"- Thermal: {therm}")
                st.markdown("---")

        with st.expander("Recommended Actions", expanded=False):
            for j, act in enumerate(actions, 1):
                priority = act.get("priority", "")
                st.markdown(f"**{j}. {act.get('action_title','')}** ({priority})")
                st.markdown(f"   {act.get('description','')}")

    except ValueError as e:
        progress_bar.progress(0)
        st.error(f"Generation failed: {e}")
    except Exception as e:
        progress_bar.progress(0)
        st.error(f"Unexpected error: {e}")
        with st.expander("Error Details"):
            st.exception(e)

st.markdown("---")
st.caption("DDR Generator · Powered by Gemini 2.5 Flash · Inspection + Thermal PDFs → Structured DDR")
