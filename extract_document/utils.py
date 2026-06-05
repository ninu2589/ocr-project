# extractor/utils.py
from google.cloud import vision
import re
from datetime import datetime
import os

# Set Google Cloud credentials
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = os.path.join(os.path.dirname(__file__), '..', 'google.json')

# Matches all common date formats:
#   05-Mar-2020  05/Mar/2020  05 Mar 2020
#   01/01/2020   01-01-2020   2020-01-01
_DATE_RE = (
    r'\d{1,2}[\/\-](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[\/\-]\d{4}'
    r'|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}'
    r'|\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4}'
    r'|\d{4}[\/\-]\d{1,2}[\/\-]\d{1,2}'
)

def _date_after(label_pattern, text):
    """Find the first date within 60 chars after a label."""
    m = re.search(label_pattern, text, re.IGNORECASE)
    if not m:
        return None
    d = re.search(_DATE_RE, text[m.end():][:60], re.IGNORECASE)
    return d.group(0) if d else None

def parse_date(date_str):
    if not date_str:
        return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%Y-%m-%d",
                "%d/%b/%Y", "%d-%b-%Y", "%d %b %Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue
    return None

def parse_amount(text):
    if not text:
        return None
    cleaned = text.replace(',', '').replace('₹', '').replace('INR', '').replace('Rs.', '').replace('Rs', '').replace('*', '').strip()
    try:
        return float(cleaned)
    except ValueError:
        return None

def extract_indian_invoice(image_path):
    client = vision.ImageAnnotatorClient()
    print(f"Extracting text from {image_path}")

    with open(image_path, 'rb') as image_file:
        content = image_file.read()

    image_ext = image_path.lower().rsplit('.', 1)[-1]
    text = ""

    if image_ext == 'pdf':
        requests = [{
            'input_config': {
                'mime_type': 'application/pdf',
                'content': content,
            },
            'features': [{'type_': vision.Feature.Type.DOCUMENT_TEXT_DETECTION}],
        }]
        response = client.batch_annotate_files(requests=requests)
        file_response = response.responses[0]

        if getattr(file_response, 'error', None) and file_response.error.message:
            print(f"Error in OCR: {file_response.error.message}")
            return {}

        page_texts = []
        for page_response in file_response.responses:
            if getattr(page_response, 'full_text_annotation', None):
                page_texts.append(page_response.full_text_annotation.text)
        text = '\n'.join(page_texts).strip()
    else:
        image = vision.Image(content=content)
        response = client.document_text_detection(image=image)

        if getattr(response, 'error', None) and response.error.message:
            print(f"Error in OCR: {response.error.message}")
            return {}

        if getattr(response, 'full_text_annotation', None) and response.full_text_annotation.text:
            text = response.full_text_annotation.text
        elif response.text_annotations:
            text = response.text_annotations[0].description

    if not text:
        print("OCR returned no text. Trying fallback text_detection.")
        image = vision.Image(content=content)
        fallback = client.text_detection(image=image)
        if getattr(fallback, 'error', None) and fallback.error.message:
            print(f"Fallback OCR error: {fallback.error.message}")
            return {}
        if fallback.text_annotations:
            text = fallback.text_annotations[0].description

    print(f"OCR text:\n{text}")

    # -------- GSTIN — capture whatever follows the "GSTIN" label --------
    gst_match = re.search(r'(?:GSTIN|GST\s*No\.?|GST\s*Number)\s*[:\-]?\s*([A-Z0-9]+)', text, re.IGNORECASE)

    # -------- Invoice / Bill number (must contain at least one digit) --------
    invoice_match = re.search(
        r'(?:Invoice\s*(?:No\.?|Number|#)?|Bill\s*No\.?)\s*[:\-]?\s*([A-Z0-9][A-Z0-9/\-]*\d[A-Z0-9/\-]*)',
        text, re.IGNORECASE
    )

    # -------- Date (priority: Proforma Date > Bill Date > standalone Date) --------
    # Negative lookbehinds prevent matching "Challan Date", "Invoice Date", etc.
    date = (
        _date_after(r'Proforma\s+Date', text) or
        _date_after(r'Bill\s+Date', text) or
        _date_after(
            r'(?<!Proforma\s)(?<!Invoice\s)(?<!Challan\s)(?<!Bill\s)(?<!Due\s)\bDate\b',
            text
        )
    )

    # -------- Amount --------
    amount = None

    label = re.search(r'Total\s+Amount\s+After\s+Tax', text, re.IGNORECASE)
    if label:
        # Grab up to 300 chars after the label; take the LAST number found
        # (table layout puts taxable/tax values before the final total)
        after = text[label.end():][:300]
        numbers = re.findall(r'[\d,]+\.\d+', after)
        if numbers:
            amount = numbers[-1]
    else:
        # Try label variants in priority order
        for label_pattern in [
            r'Total\s+Amount',
            r'Amount\s+Due',
            r'Total\s+Due',
            r'Amount\s+(?:in\s+)?INR',
            r'Total',
        ]:
            m = re.search(
                label_pattern + r'[\s\n]*[:\-]?[\s\n]*(?:₹|INR|Rs\.?)?\s*([\d,]+\.\d+)',
                text, re.IGNORECASE
            )
            if m:
                amount = m.group(1)
                break

    return {
        "gst":        gst_match.group(1).strip() if gst_match else None,
        "invoice_no": invoice_match.group(1).strip() if invoice_match else None,
        "date":       date,
        "amount":     amount,
        "raw_text":   text,
    }
