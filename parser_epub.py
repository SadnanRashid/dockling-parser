import pypandoc
from pathlib import Path

# Try to download pandoc if not found
try:
    pypandoc.get_pandoc_version()
except OSError:
    print("Pandoc not found. Downloading...")
    pypandoc.download_pandoc()

# Input EPUB file
INPUT_EPUB = Path("famouspaintings.epub")
OUT_DIR = Path("output")
OUT_DIR.mkdir(exist_ok=True)

MEDIA_DIR = OUT_DIR / "media"
MEDIA_DIR.mkdir(exist_ok=True)

MD_FILE = OUT_DIR / "famouspaintings.md"
HTML_FILE = OUT_DIR / "famouspaintings.html"

if not INPUT_EPUB.exists():
    print(f"Error: File '{INPUT_EPUB}' not found!")
    exit(1)

print(f"Converting '{INPUT_EPUB}' to Markdown...")

try:
    # Convert EPUB to Markdown with media extraction
    pypandoc.convert_file(
        str(INPUT_EPUB),
        'md',
        outputfile=str(MD_FILE),
        extra_args=[f"--extract-media={MEDIA_DIR}"]
    )
    
    print(f"Markdown conversion successful!")
    print(f"Markdown: {MD_FILE}")
    
    # Convert Markdown to HTML
    print(f"\nConverting to HTML...")
    pypandoc.convert_file(
        str(MD_FILE),
        'html',
        outputfile=str(HTML_FILE),
        extra_args=['--standalone', '--self-contained']
    )
    
    print(f"HTML conversion successful!")
    print(f"HTML: {HTML_FILE}")
    print(f"Media: {MEDIA_DIR}")
    
except Exception as e:
    print(f"Conversion failed: {e}")
    exit(1)