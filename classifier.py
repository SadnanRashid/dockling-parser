# classifier.py
import logging
import base64
import json
from pathlib import Path
from typing import Dict, List, Optional
import fitz  # PyMuPDF
from PIL import Image
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("classifier")


def encode_image_to_base64(image_path: Path) -> str:
    """Convert image to base64."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


def pdf_to_images(pdf_path: Path, output_dir: Path) -> List[Path]:
    """
    Convert PDF to images using PyMuPDF.
    """
    logger.info(f"Converting PDF to images: {pdf_path.name}")
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        pdf_document = fitz.open(str(pdf_path))
        image_paths = []
        pdf_stem = pdf_path.stem
        
        for page_num in range(len(pdf_document)):
            page = pdf_document[page_num]
            mat = fitz.Matrix(2, 2)
            pix = page.get_pixmap(matrix=mat)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            
            img_path = output_dir / f"{pdf_stem}_page_{page_num + 1}.png"
            img.save(str(img_path), 'PNG')
            image_paths.append(img_path)
            logger.info(f"  Saved page {page_num + 1}: {img_path.name}")
        
        pdf_document.close()
        return image_paths
        
    except Exception as e:
        logger.error(f"Failed to convert PDF: {e}")
        raise


def classify_document(image_paths: List[Path], rules_text: str) -> Optional[Dict]:
    """
    Classify the ENTIRE document by analyzing all pages together.
    Returns document-level classification.
    """
    try:
        vision_model = ChatOpenAI(
            model="gpt-4o",
            temperature=0,
            max_tokens=4096
        )
        
        # Prepare all images for multi-image analysis
        content = [
            {"type": "text", "text": f"""You are an intelligent document classification system.

VALIDATION RULES:
{rules_text}

YOU ARE ANALYZING A COMPLETE DOCUMENT WITH {len(image_paths)} PAGE(S).

YOUR TASK:
Analyze ALL pages together to determine the OVERALL document type. All pages belong to the SAME document.

DOCUMENT TYPES:
- INVOICE: Bills, invoices, purchase orders, payment requests
- CONTRACT: Agreements, terms and conditions, legal contracts
- REPORT: Business reports, analytics, summaries, dashboards
- FORM: Application forms, registration forms, questionnaires
- POLICY: Insurance policies, company policies, procedures, guidelines
- CERTIFICATE: Certificates, licenses, credentials
- LETTER: Business letters, correspondence, notices
- RECEIPT: Payment receipts, transaction records
- OTHER: If none of the above fit

CLASSIFICATION LOGIC:
- Consider ALL pages together - they are part of ONE document
- First page usually has document title/header
- Subsequent pages may have details, terms, line items, etc.
- Look for consistent themes across all pages
- A 3-page invoice will have: header (p1), line items (p2), terms (p3) - ALL are invoice pages

OUTPUT FORMAT (return valid JSON only):
{{
    "document_classification": {{
        "document_type": "INVOICE|CONTRACT|REPORT|FORM|POLICY|CERTIFICATE|LETTER|RECEIPT|OTHER",
        "confidence": "HIGH|MEDIUM|LOW",
        "reasoning": "Explain your classification based on evidence from ALL pages"
    }},
    "validation": {{
        "status": "PASS|FAIL",
        "reasoning": "Does this document meet the validation rules?"
    }},
    "document_summary": "Overall description of what this document is about"
}}

Be thorough and consider the document as a whole.
IMPORTANT: Return ONLY the JSON object. Do NOT wrap it in markdown code blocks or backticks."""}
        ]
        
        # Add all page images
        for img_path in image_paths:
            base64_image = encode_image_to_base64(img_path)
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{base64_image}"}
            })
        
        message = HumanMessage(content=content)
        response = vision_model.invoke([message])
        response_text = response.content.strip()

        # Clean up JSON formatting
        if "```json" in content:
            content = content.replace("```json", "").replace("```", "")
        elif "```" in content:
            content = content.replace("```", "") 
        
        result = json.loads(response_text)
        return result
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing error: {e}")
        logger.error(f"Raw response: {response_text}")
        return None
    except Exception as e:
        logger.error(f"Classification error: {e}")
        return None


def extract_page_data(image_path: Path, page_num: int, document_type: str) -> Optional[Dict]:
    """
    Extract structured data from a single page.
    Page is already classified as part of document_type.
    """
    try:
        vision_model = ChatOpenAI(
            model="gpt-4o",
            temperature=0,
            max_tokens=4096
        )
        
        base64_image = encode_image_to_base64(image_path)
        
        prompt = f"""You are extracting data from page {page_num} of a {document_type} document.

YOUR TASK:
Extract all relevant information from this page. This page is part of a {document_type}.

OUTPUT FORMAT (return valid JSON only):
{{
    "extracted_data": {{
        "text_content": ["key text visible on page"],
        "key_fields": {{
            "document_number": "if visible",
            "date": "if visible",
            "company_name": "if visible",
            "amounts": ["if visible"],
            "parties_involved": ["if visible"],
            "signatures": "if visible",
            "any_other_relevant_fields": "extract what makes sense"
        }},
        "detected_elements": ["tables", "signatures", "logos", "stamps", "charts", "etc"]
    }},
    "page_summary": "Brief description of what this specific page contains"
}}

Be thorough in extraction.
IMPORTANT: Return ONLY the JSON object. Do NOT wrap it in markdown code blocks or backticks."""

        message = HumanMessage(
            content=[
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
            ]
        )
        
        response = vision_model.invoke([message])
        content = response.content.strip()
        
        if "```json" in content:
            content = content.replace("```json", "").replace("```", "")
        elif "```" in content:
            content = content.replace("```", "")
        
        result = json.loads(content)
        return result
        
    except Exception as e:
        logger.error(f"Extraction error for page {page_num}: {e}")
        return None


def process_pdf(
    pdf_path: Path,
    rules_text: str,
    base_output_dir: Path,
    temp_images_dir: Path
) -> Dict:
    """
    Process a PDF: classify document, extract page data, organize by type.
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"Processing: {pdf_path.name}")
    logger.info(f"{'='*60}")
    
    # Convert PDF to images
    pdf_images_dir = temp_images_dir / pdf_path.stem
    image_paths = pdf_to_images(pdf_path, pdf_images_dir)
    logger.info(f"Converted to {len(image_paths)} page images\n")
    
    # STEP 1: Classify the entire document
    logger.info("Classifying document (analyzing all pages together)...")
    classification_result = classify_document(image_paths, rules_text)
    
    if not classification_result:
        logger.error("Document classification failed")
        return None
    
    document_type = classification_result["document_classification"]["document_type"]
    confidence = classification_result["document_classification"]["confidence"]
    validation_status = classification_result["validation"]["status"]
    
    logger.info(f"Document Type: {document_type}")
    logger.info(f"Confidence: {confidence}")
    logger.info(f"Validation: {validation_status}\n")
    
    # STEP 2: Extract data from each page
    logger.info("Extracting data from individual pages...")
    page_results = []
    
    for idx, img_path in enumerate(image_paths, 1):
        logger.info(f"[{idx}/{len(image_paths)}] Extracting: {img_path.name}...")
        
        page_data = extract_page_data(img_path, idx, document_type)
        
        if page_data:
            page_data["page_number"] = idx
            page_data["image_file"] = img_path.name
            page_results.append(page_data)
            logger.info(f"  → Extracted successfully")
        else:
            logger.warning(f"  → Extraction failed")
    
    # STEP 3: Generate report
    report = {
        "pdf_file": pdf_path.name,
        "document_classification": classification_result["document_classification"],
        "validation": classification_result["validation"],
        "document_summary": classification_result.get("document_summary", ""),
        "total_pages": len(image_paths),
        "rules_used": rules_text,
        "page_results": page_results
    }
    
    # STEP 4: Save report in document-type folder
    type_output_dir = base_output_dir / document_type
    type_output_dir.mkdir(parents=True, exist_ok=True)
    
    report_file = type_output_dir / f"{pdf_path.stem}_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    logger.info(f"\n{'='*60}")
    logger.info(f"SUMMARY: {pdf_path.name}")
    logger.info(f"{'='*60}")
    logger.info(f"Document Type: {document_type}")
    logger.info(f"Confidence: {confidence}")
    logger.info(f"Validation: {validation_status}")
    logger.info(f"Total Pages: {len(image_paths)}")
    logger.info(f"Report saved: {report_file}")
    logger.info(f"{'='*60}\n")
    
    return report


def read_rules(rules_file: str = "rules.txt") -> str:
    """Read validation rules from text file."""
    rules_path = Path(rules_file)
    if not rules_path.exists():
        raise FileNotFoundError(f"{rules_file} not found.")
    
    with open(rules_path, "r", encoding="utf-8") as f:
        rules = f.read().strip()
    
    if not rules:
        raise ValueError(f"{rules_file} is empty.")
    
    return rules
