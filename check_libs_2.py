
try:
    from docling.datamodel.base_models import InputFormat
    print("InputFormat members:", [m.name for m in InputFormat])
except ImportError as e:
    print("Could not import InputFormat:", e)

try:
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    opts = dir(PdfPipelineOptions)
    ocr_opts = [o for o in opts if "ocr" in o.lower()]
    print("PdfPipelineOptions OCR related:", ocr_opts)
    print("PdfPipelineOptions all:", opts)
except ImportError as e:
    print("Could not import PdfPipelineOptions:", e)
