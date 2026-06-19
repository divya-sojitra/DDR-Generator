# DDR Generator

AI-powered Detailed Diagnostic Report generator for property inspections.

Upload an Inspection Report PDF and a Thermal Images PDF → Gemini 2.5 Flash analyzes both → Download a structured, professionally formatted DDR PDF with embedded images.

## Tech Stack

- **Google Gemini 2.5 Flash** — Native multimodal PDF understanding; reads text, images, and layout without pre-processing
- **PyMuPDF (fitz)** — Fast, low-level image extraction from PDFs
- **ReportLab** — Programmatic PDF assembly with precise layout control
- **Streamlit** — Rapid web UI with file upload, progress tracking, and download

## Setup

```bash
# 1. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Mac/Linux
# venv\Scripts\activate         # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure your API key
cp .env.example .env
# Edit .env and set GEMINI_API_KEY=your_real_key_here
# Get a key at: https://aistudio.google.com/app/apikey

# 4. Run the app
streamlit run app.py
```

The app opens at `http://localhost:8501`.

You can also enter the API key directly in the sidebar instead of using `.env`.

## Pipeline

```
Upload PDFs
    │
    ▼
extract_images_smart()        ← PyMuPDF: deduplicated image extraction
    │
    ▼
generate_ddr()                ← Gemini 2.5 Flash Files API: both PDFs analyzed together
    │                            Returns structured JSON with 8 DDR sections
    ▼
build_ddr_pdf()               ← ReportLab: assembles PDF with tables, images, color-coded sections
    │
    ▼
Download DDR PDF
```

## Design Decisions

**Why Gemini for analysis instead of extracting text and passing it?**
Gemini 2.5 Flash accepts raw PDF bytes via the Files API and natively understands document layout, embedded images, tables, and handwriting. Passing pre-extracted text would lose spatial relationships between observations and IR images — Gemini can directly correlate a cold spot in a thermal image with the corresponding dampness note in the inspection report.

**Why smart image deduplication?**
Thermal PDFs often embed the same branding logo or background element hundreds of times (one per page). Without deduplication using `(width, height, byte_length)` as a key, extraction would return 500+ copies of the same 40 KB logo, consuming gigabytes of memory and hitting the max_images cap before capturing any real thermography content.

**Why keyword-based image matching in the PDF builder?**
Gemini returns area names and image captions from the documents. The PDF builder scores extracted images by how many area/caption keywords appear in each image's label (which encodes its page and position). This connects the right thermal or inspection photo to each area's section in the output PDF without requiring manual tagging.

## Project Structure

```
ddr-generator/
├── app.py           # Streamlit UI — upload, progress, download
├── extractor.py     # PyMuPDF image extraction (basic + smart)
├── generator.py     # Gemini 2.5 Flash API integration
├── pdf_builder.py   # ReportLab PDF assembly with images
├── utils.py         # Shared helpers (API key, logging, formatting)
├── requirements.txt
├── .env.example
└── README.md
```
