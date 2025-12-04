# classifier.py
import logging
import base64
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import fitz  
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv
from PIL import Image
import io

load_dotenv()

logger = logging.getLogger("classifier")


def encode_image_to_base64(image_path: Path) -> str:
    """Convert image to base64."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


# Replace the pdf_to_images function with this:
def pdf_to_images(pdf_path: Path, output_dir: Path) -> List[Path]:
    """
    Convert PDF to images using PyMuPDF.
    
    Args:
        pdf_path: Path to PDF file
        output_dir: Directory to save images
        
    Returns:
        List of image file paths
    """
    logger.info(f"Converting PDF to images: {pdf_path.name}")
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Open PDF
        pdf_document = fitz.open(str(pdf_path))
        
        image_paths = []
        pdf_stem = pdf_path.stem
        
        for page_num in range(len(pdf_document)):
            # Get page
            page = pdf_document[page_num]
            
            # Render page to image (zoom=2 for 200 DPI equivalent)
            mat = fitz.Matrix(2, 2)
            pix = page.get_pixmap(matrix=mat)
            
            # Convert to PIL Image
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            
            # Save image
            img_path = output_dir / f"{pdf_stem}_page_{page_num + 1}.png"
            img.save(str(img_path), 'PNG')
            image_paths.append(img_path)
            logger.info(f"  Saved page {page_num + 1}: {img_path.name}")
        
        pdf_document.close()
        return image_paths
        
    except Exception as e:
        logger.error(f"Failed to convert PDF: {e}")
        raise


def classify_and_extract(image_path: Path, rules_text: str) -> Optional[Dict]:
    """
    Classify document type and extract information using GPT-4o vision.
    
    Args:
        image_path: Path to the image file
        rules_text: Validation rules as string
        
    Returns:
        Dictionary with classification and extraction results
    """
    try:
        vision_model = ChatOpenAI(
            model="gpt-4o",
            temperature=0,
            max_tokens=4096
        )
        
        base64_image = encode_image_to_base64(image_path)
        
        prompt = f"""You are an intelligent document classification and extraction system.

VALIDATION RULES:
{rules_text}

YOUR TASKS:

1. DOCUMENT CLASSIFICATION
Classify this document page into ONE of these categories:
- INVOICE: Bills, invoices, purchase orders, payment requests
- CONTRACT: Agreements, terms and conditions, legal contracts
- REPORT: Business reports, analytics, summaries, dashboards
- FORM: Application forms, registration forms, questionnaires
- POLICY: Insurance policies, company policies, procedures, guidelines
- CERTIFICATE: Certificates, licenses, credentials
- LETTER: Business letters, correspondence, notices
- RECEIPT: Payment receipts, transaction records
- OTHER: If none of the above fit

Classification Logic:
- Look for keywords: "INVOICE", "CONTRACT", "AGREEMENT", "REPORT", "POLICY", "FORM", etc.
- Analyze layout: Tables with amounts = likely invoice, signature blocks = likely contract
- Check structure: Forms have fillable fields, reports have charts/data
- Consider content: Legal language = contract, financial data = invoice/report

2. VALIDATION
Check if this document meets the validation rules provided above.

3. INFORMATION EXTRACTION
Extract all relevant information from the document.

OUTPUT FORMAT (return valid JSON only):
{{
    "document_classification": {{
        "primary_type": "INVOICE|CONTRACT|REPORT|FORM|POLICY|CERTIFICATE|LETTER|RECEIPT|OTHER",
        "confidence": "HIGH|MEDIUM|LOW",
        "reasoning": "Explain why you classified it this way - mention keywords found, layout patterns, or structural clues"
    }},
    "validation": {{
        "status": "PASS|FAIL",
        "reasoning": "Does it meet the validation rules?"
    }},
    "extracted_data": {{
        "text_content": ["key text found"],
        "key_fields": {{
            "document_number": "if applicable",
            "date": "if found",
            "company_name": "if found",
            "amounts": ["if applicable"],
            "parties_involved": ["if applicable"]
        }},
        "detected_elements": ["tables", "signatures", "logos", "stamps", "etc"]
    }},
    "page_summary": "Brief description of what this page contains"
}}

Be thorough and accurate in classification."""

        message = HumanMessage(
            content=[
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
            ]
        )
        
        response = vision_model.invoke([message])
        content = response.content.strip()
        
        # Clean up JSON formatting
        if "```json" in content:
            content = content.replace("```json", "").replace("```", "")
        elif "```" in content:
            content = content.replace("```", "")
        
        result = json.loads(content)
        return result
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing error for {image_path.name}: {e}")
        logger.error(f"Raw response: {content}")
        return None
    except Exception as e:
        logger.error(f"Classification error for {image_path.name}: {e}")
        return None


def process_pdf(
    pdf_path: Path,
    rules_text: str,
    output_dir: Path,
    temp_images_dir: Path
) -> Dict:
    """
    Process a single PDF: convert to images, classify, extract, and generate report.
    
    Args:
        pdf_path: Path to PDF file
        rules_text: Validation rules
        output_dir: Directory for output report
        temp_images_dir: Directory for temporary images
        
    Returns:
        Dictionary containing complete processing report
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"Processing: {pdf_path.name}")
    logger.info(f"{'='*60}")
    
    # Convert PDF to images
    image_paths = pdf_to_images(pdf_path, temp_images_dir)
    logger.info(f"Converted to {len(image_paths)} page images\n")
    
    # Process each page
    results = []
    document_types = []
    
    for idx, img_path in enumerate(image_paths, 1):
        logger.info(f"[{idx}/{len(image_paths)}] Classifying: {img_path.name}...")
        
        result = classify_and_extract(img_path, rules_text)
        
        if result:
            result["page_number"] = idx
            result["image_file"] = img_path.name
            results.append(result)
            
            doc_type = result["document_classification"]["primary_type"]
            document_types.append(doc_type)
            
            logger.info(f"  → Type: {doc_type}")
            logger.info(f"  → Confidence: {result['document_classification']['confidence']}")
            logger.info(f"  → Validation: {result['validation']['status']}")
        else:
            logger.warning(f"  → ERROR: Classification failed")
    
    # Determine overall document type (majority vote)
    if document_types:
        from collections import Counter
        type_counts = Counter(document_types)
        overall_type = type_counts.most_common(1)
        type_distribution = dict(type_counts)
    else:
        overall_type = "UNKNOWN"
        type_distribution = {}
    
    # Generate report
    report = {
        "pdf_file": pdf_path.name,
        "total_pages": len(image_paths),
        "overall_classification": {
            "document_type": overall_type,
            "type_distribution": type_distribution
        },
        "rules_used": rules_text,
        "page_results": results
    }
    
    # Save report
    report_file = output_dir / f"{pdf_path.stem}_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    logger.info(f"\n{'='*60}")
    logger.info(f"SUMMARY: {pdf_path.name}")
    logger.info(f"{'='*60}")
    logger.info(f"Overall Document Type: {overall_type}")
    logger.info(f"Total Pages: {len(image_paths)}")
    logger.info(f"Type Distribution: {type_distribution}")
    logger.info(f"Report saved: {report_file}")
    logger.info(f"{'='*60}\n")
    
    return report


def read_rules(rules_file: str = "rules.txt") -> str:
    """Read validation rules from text file."""
    rules_path = Path(rules_file)
    if not rules_path.exists():
        raise FileNotFoundError(f"{rules_file} not found. Please create it with your validation rules.")
    
    with open(rules_path, "r", encoding="utf-8") as f:
        rules = f.read().strip()
    
    if not rules:
        raise ValueError(f"{rules_file} is empty. Please add validation rules.")
    
    return rules
