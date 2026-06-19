"""
generator.py
Sends both PDFs to Gemini 2.5 Flash as multimodal input via the Files API.
Returns a structured DDR dict parsed from JSON.
Uses the new google-genai SDK (replaces deprecated google-generativeai).
"""

from google import genai
from google.genai import types
import io
import json
import re
import logging
import time

logger = logging.getLogger(__name__)

DDR_PROMPT = """
You are an expert property inspection analyst. You have been given TWO documents:
1. An Inspection Report (containing visual observations, site data, and checklist inputs)
2. A Thermal Report (containing IR thermography images with temperature readings)

Your task is to analyze BOTH documents thoroughly and generate a comprehensive Detailed Diagnostic Report (DDR).

STRICT RULES:
- Do NOT invent any facts not present in the documents.
- If information conflicts between documents, mention the conflict explicitly.
- If information is missing, write exactly: "Not Available"
- Use simple, client-friendly language. Avoid unnecessary technical jargon.
- Avoid duplicate points across sections.
- Combine and correlate data logically (e.g., link thermal cold spots to dampness observations).

Return your response as a VALID JSON object with EXACTLY this structure:

{
  "report_metadata": {
    "property_address": "string",
    "inspection_date": "string",
    "inspected_by": "string",
    "report_date": "string",
    "property_type": "string",
    "year_of_construction": "string",
    "building_age": "string",
    "previous_audit": "string",
    "previous_repairs": "string"
  },
  "property_issue_summary": {
    "overview": "string (2-4 sentence overall summary of the property's health)",
    "total_issues_found": "number",
    "critical_issues": ["list of critical issue strings"],
    "moderate_issues": ["list of moderate issue strings"]
  },
  "area_wise_observations": [
    {
      "area_name": "string (e.g., Hall - Ground Floor, Master Bedroom Bathroom - 1st Floor)",
      "negative_side": "string (what problems are visible on the impacted side)",
      "positive_side": "string (source/cause found on exposed side)",
      "thermal_reading": "string (temperature data from thermal report if available, else 'Not Available')",
      "thermal_interpretation": "string (what the thermal reading indicates, else 'Not Available')",
      "image_captions": ["list of image caption strings relevant to this area, exactly as described in the documents"]
    }
  ],
  "probable_root_cause": {
    "primary_cause": "string",
    "contributing_factors": ["list of contributing factor strings"],
    "cause_explanation": "string (2-3 sentences explaining the cause chain)"
  },
  "severity_assessment": [
    {
      "area": "string",
      "severity": "Critical | High | Moderate | Low",
      "reasoning": "string (why this severity level was assigned)"
    }
  ],
  "recommended_actions": [
    {
      "action_title": "string",
      "applies_to": ["list of area names"],
      "description": "string (what to do, in plain language)",
      "priority": "Immediate | Short-term | Long-term"
    }
  ],
  "additional_notes": [
    "string (each note as a separate list item)"
  ],
  "missing_or_unclear_information": [
    "string (each missing/unclear item as a separate list item, or single item 'Not Available' if nothing is missing)"
  ]
}

IMPORTANT: Return ONLY the JSON object. No markdown, no code fences, no explanation text before or after.
"""


def _build_client(api_key: str) -> genai.Client:
    return genai.Client(api_key=api_key)


def _upload_pdf(client: genai.Client, pdf_bytes: bytes, display_name: str):
    """Upload PDF bytes to Gemini Files API and return the file object."""
    file_obj = io.BytesIO(pdf_bytes)
    uploaded = client.files.upload(
        file=file_obj,
        config=types.UploadFileConfig(
            mime_type="application/pdf",
            display_name=display_name,
        ),
    )
    logger.info(f"Uploaded '{display_name}' → {uploaded.name}")
    return uploaded


def _wait_active(client: genai.Client, file, timeout: int = 120):
    """Poll until the uploaded file is ACTIVE."""
    start = time.time()
    while True:
        state = file.state.name if hasattr(file.state, "name") else str(file.state)
        if state == "ACTIVE":
            return file
        if time.time() - start > timeout:
            raise TimeoutError(f"File {file.name} did not become ACTIVE within {timeout}s")
        if state == "FAILED":
            raise ValueError(f"File {file.name} processing failed.")
        time.sleep(3)
        file = client.files.get(name=file.name)


def generate_ddr(
    api_key: str,
    inspection_pdf_bytes: bytes,
    thermal_pdf_bytes: bytes,
    property_name: str = "Property",
) -> dict:
    """
    Main entry point: sends both PDFs to Gemini and returns parsed DDR dict.
    Raises ValueError on JSON parse failure, TimeoutError on file processing timeout.
    """
    client = _build_client(api_key)

    logger.info("Uploading Inspection PDF to Gemini Files API...")
    insp_file = _upload_pdf(client, inspection_pdf_bytes, f"inspection_report_{property_name}.pdf")
    insp_file = _wait_active(client, insp_file)

    logger.info("Uploading Thermal PDF to Gemini Files API...")
    thermal_file = _upload_pdf(client, thermal_pdf_bytes, f"thermal_report_{property_name}.pdf")
    thermal_file = _wait_active(client, thermal_file)

    logger.info("Sending both PDFs to Gemini 2.5 Flash for DDR generation...")

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            "DOCUMENT 1 - INSPECTION REPORT:",
            insp_file,
            "DOCUMENT 2 - THERMAL IMAGES REPORT:",
            thermal_file,
            DDR_PROMPT,
        ],
        config=types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=65536,
        ),
    )

    raw_text = response.text.strip()
    logger.info(f"Received response ({len(raw_text)} chars)")

    # Strip markdown fences if present
    raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text, flags=re.MULTILINE)
    raw_text = re.sub(r"\s*```\s*$", "", raw_text, flags=re.MULTILINE)
    raw_text = raw_text.strip()

    # Extract the outermost JSON object in case there's surrounding text
    match = re.search(r"\{.*\}", raw_text, re.DOTALL)
    if match:
        raw_text = match.group(0)

    try:
        ddr_data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error: {e}\nRaw snippet:\n{raw_text[:500]}")
        raise ValueError(
            f"Gemini returned invalid JSON. Raw response starts with:\n{raw_text[:300]}"
        ) from e

    # Cleanup uploaded files to avoid quota buildup
    try:
        client.files.delete(name=insp_file.name)
        client.files.delete(name=thermal_file.name)
        logger.info("Cleaned up uploaded files from Gemini.")
    except Exception:
        pass

    return ddr_data
