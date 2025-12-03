
try:
    from docling.datamodel.base_models import InputFormat
    print("InputFormat members:", [m.name for m in InputFormat])
except ImportError as e:
    print("Could not import InputFormat:", e)

try:
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    print("PdfPipelineOptions attributes:", dir(PdfPipelineOptions))
except ImportError as e:
    print("Could not import PdfPipelineOptions:", e)

try:
    import pytesseract
    print("pytesseract is available")
except ImportError:
    print("pytesseract is NOT available")

try:
    import easyocr
    print("easyocr is available")
except ImportError:
    print("easyocr is NOT available")
