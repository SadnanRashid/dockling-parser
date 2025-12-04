# main.py
import logging
from pathlib import Path
from classifier import read_rules, process_pdf

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("main")


def main():
    """
    Main entry point:
    1. Load validation rules
    2. Find all PDFs in input_pdfs/
    3. Process each PDF: classify document, extract page data
    4. Save reports organized by document type in output/
    """
    
    # Setup directories
    input_dir = Path("input_pdfs")
    output_dir = Path("output")
    temp_images_dir = Path("output/temp_images")
    
    input_dir.mkdir(exist_ok=True)
    output_dir.mkdir(exist_ok=True)
    temp_images_dir.mkdir(parents=True, exist_ok=True)
    
    # Load rules
    logger.info("Loading validation rules...")
    try:
        rules_text = read_rules("rules.txt")
        logger.info(f"Rules loaded:\n{rules_text}\n")
    except Exception as e:
        logger.error(f"Failed to load rules: {e}")
        return
    
    # Find PDFs
    pdf_files = list(input_dir.glob("*.pdf"))
    
    if not pdf_files:
        logger.warning(f"No PDF files found in {input_dir}/")
        logger.info("Please place PDF files in the input_pdfs/ folder")
        return
    
    logger.info(f"Found {len(pdf_files)} PDF file(s) to process\n")
    
    # Process each PDF
    all_reports = []
    
    for pdf_path in pdf_files:
        try:
            report = process_pdf(
                pdf_path=pdf_path,
                rules_text=rules_text,
                base_output_dir=output_dir,  
                temp_images_dir=temp_images_dir
            )
            
            if report:
                all_reports.append(report)
            
        except Exception as e:
            logger.error(f"Failed to process {pdf_path.name}: {e}")
            continue
    
    # Summary
    logger.info("\n" + "="*60)
    logger.info("BATCH PROCESSING COMPLETE")
    logger.info("="*60)
    logger.info(f"Total PDFs processed: {len(all_reports)}")
    logger.info(f"Reports organized by type in: {output_dir}")
    logger.info(f"Page images saved in: {temp_images_dir}")
    logger.info("="*60)


if __name__ == "__main__":
    main()
