from docling.datamodel.base_models import InputFormat
from docling.document_converter import DocumentConverter
from pathlib import Path

# Initialize converter
converter = DocumentConverter()

# Input file (supports .csv, .xlsx, .xls)
INP_FILE = "sample_data.xlsx"

# Output directory
OUT_DIR = Path("out")
OUT_DIR.mkdir(exist_ok=True)

# Get input file path
input_path = Path(INP_FILE)

# Check if file exists
if not input_path.exists():
    print(f"Error: File '{INP_FILE}' not found!")
    exit(1)

# Get file extension
file_ext = input_path.suffix.lower()

# Supported formats
supported_formats = ['.csv', '.xlsx', '.xls']

if file_ext not in supported_formats:
    print(f"Error: Unsupported format '{file_ext}'")
    print(f"Supported: {', '.join(supported_formats)}")
    exit(1)

print(f"Converting '{INP_FILE}'...")

try:
    # Convert the document (removed quotes around INP_FILE)
    res = converter.convert(str(input_path))
    
    # Create output filenames based on input filename
    base_name = input_path.stem  # filename without extension
    md_file = OUT_DIR / f"{base_name}.md"
    html_file = OUT_DIR / f"{base_name}.html"
    
    # Save as Markdown
    print(f"Saving Markdown...")
    res.document.save_as_markdown(str(md_file))
    
    # Save as HTML
    print(f"Saving HTML...")
    res.document.save_as_html(str(html_file))
    
    print(f"\nConversion successful!")
    print(f"Markdown: {md_file}")
    print(f"HTML: {html_file}")
    print(f"Output dir: {OUT_DIR}")
    
except Exception as e:
    print(f"Conversion failed: {e}")
    exit(1)