import logging
import os
import re
import shutil
import urllib.parse
import warnings
from pathlib import Path

import pandas as pd
import pdfplumber
from docling_core.types.doc import ImageRefMode, PictureItem, TableItem
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

warnings.filterwarnings("ignore", category=UserWarning)

INPUT_PDF = Path("Semester-VII.pdf")
OUT_DIR = Path("Semester-VII")

# Subfolders for different types of images
PAGES_SUBFOLDER = "pages"
FIGURES_SUBFOLDER = "figures"
TABLES_SUBFOLDER = "tables"
CSV_SUBFOLDER = "extracted_csv"

OUT_DIR.mkdir(parents=True, exist_ok=True)
IMAGE_RESOLUTION_SCALE = 2.0

logger = logging.getLogger("parser")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


copied_images_cache = {}  # key = absolute path → value = rel path inside images folder


def _ensure_images_dir(out_dir: Path, subfolder: str) -> Path:
    p = out_dir / subfolder
    p.mkdir(parents=True, exist_ok=True)
    return p


def _copy_into_images(found: Path, out_dir: Path, images_dir: Path) -> str:
    """
    Copy file once. If already copied earlier, reuse path from cache.
    """
    fpath = found.resolve()

    # CACHE HIT → already copied
    if fpath in copied_images_cache:
        return copied_images_cache[fpath]

    # First-time copy
    dest = images_dir / found.name
    i = 1
    while dest.exists():
        dest = images_dir / f"{found.stem}_{i}{found.suffix}"
        i += 1

    shutil.copy2(found, dest)
    rel = os.path.relpath(dest, start=out_dir).replace("\\", "/")
    copied_images_cache[fpath] = rel
    return rel


def _fix_html_image_refs(html_path: Path, out_dir: Path):
    html = html_path.read_text(encoding="utf-8")
    html = urllib.parse.unquote(html)
    src_re = re.compile(r'src=(["\'])(.*?)\1', flags=re.IGNORECASE)

    def repl(m):
        orig = m.group(2)

        if orig.startswith(("data:", "http://", "https://")):
            return m.group(0)

        decoded = orig.replace("\\", "/")
        candidates = [Path(decoded), out_dir / decoded, Path.cwd() / decoded]

        found = None
        for c in candidates:
            try:
                if c.exists():
                    found = c.resolve()
                    break
            except:
                pass

        if not found:
            name = Path(decoded).name
            for p in out_dir.rglob(name):
                found = p.resolve()
                break

        if not found:
            return f'src="{decoded}"'

        rel = _copy_into_images(found, out_dir, found.parent)
        return f'src="{rel}"'

    fixed = src_re.sub(repl, html)
    html_path.write_text(fixed, encoding="utf-8")
    return html_path


def _fix_markdown_image_refs(md_path: Path, out_dir: Path):
    text = md_path.read_text(encoding="utf-8")
    md_img_re = re.compile(r'!\[([^\]]*)\]\((.*?)\)')

    def repl(m):
        alt = m.group(1)
        url = m.group(2).strip()
        parts = re.split(r'\s+["\']', url, maxsplit=1)
        url_part = parts[0].rstrip('"').rstrip("'")

        if url_part.startswith(("data:", "http://", "https://")):
            return m.group(0)

        decoded = urllib.parse.unquote(url_part).replace("\\", "/")
        candidates = [Path(decoded), out_dir / decoded, Path.cwd() / decoded]

        found = None
        for c in candidates:
            if c.exists():
                found = c.resolve()
                break

        if not found:
            fname = Path(decoded).name
            for p in out_dir.rglob(fname):
                found = p.resolve()
                break

        if not found:
            return f'![{alt}]({decoded})'

        rel = _copy_into_images(found, out_dir, found.parent)
        return f'![{alt}]({rel})'

    fixed = md_img_re.sub(repl, text)
    md_path.write_text(fixed, encoding="utf-8")
    return md_path


def extract_tables_with_pdfplumber(pdf_path: Path, csv_dir: Path) -> list:
    """
    Extract tables from PDF using pdfplumber and save as CSV files.
    Returns list of CSV file paths.
    """
    csv_files = []
    logger.info("extracting tables with pdfplumber from %s", pdf_path.name)
    
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables()
            for idx, table in enumerate(tables, start=1):
                if table:  # Only process non-empty tables
                    csv_filename = f"table_page{page_num}_{idx}.csv"
                    csv_path = csv_dir / csv_filename
                    
                    # Convert to DataFrame and save
                    df = pd.DataFrame(table)
                    df.to_csv(csv_path, index=False, header=False)
                    
                    csv_files.append(csv_path)
                    logger.info("extracted table from page %d (table %d)", page_num, idx)
    
    logger.info("total tables extracted: %d", len(csv_files))
    return csv_files


def csv_to_html_table(csv_path: Path) -> str:
    """Convert CSV file to HTML table string."""
    df = pd.read_csv(csv_path, header=None)
    
    html = '<table border="1" style="border-collapse: collapse; margin: 20px 0;">\n'
    
    # Add rows
    for _, row in df.iterrows():
        html += '  <tr>\n'
        for cell in row:
            html += f'    <td style="padding: 8px;">{cell}</td>\n'
        html += '  </tr>\n'
    
    html += '</table>\n'
    return html


def csv_to_markdown_table(csv_path: Path) -> str:
    """Convert CSV file to Markdown table string."""
    df = pd.read_csv(csv_path, header=None)
    
    if df.empty:
        return ""
    
    # Build markdown table
    lines = []
    
    # First row
    lines.append("| " + " | ".join(str(cell) for cell in df.iloc[0]) + " |")
    
    # Separator
    lines.append("| " + " | ".join(["---"] * len(df.columns)) + " |")
    
    # Remaining rows
    for _, row in df.iloc[1:].iterrows():
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    
    return "\n".join(lines) + "\n\n"


def append_csv_tables_to_html(html_path: Path, csv_files: list):
    """Append CSV tables to the end of HTML file."""
    html = html_path.read_text(encoding="utf-8")
    
    # Find the closing body tag or append at end
    if "</body>" in html:
        insert_pos = html.rfind("</body>")
    else:
        insert_pos = len(html)
    
    # Build tables section
    tables_html = '\n<hr>\n<h2>Extracted Tables (CSV)</h2>\n'
    
    for csv_path in csv_files:
        rel_path = os.path.relpath(csv_path, start=html_path.parent).replace("\\", "/")
        tables_html += f'<h3>{csv_path.name}</h3>\n'
        tables_html += f'<p><a href="{rel_path}">Download CSV</a></p>\n'
        tables_html += csv_to_html_table(csv_path)
        tables_html += '\n'
    
    # Insert before closing body tag or at end
    new_html = html[:insert_pos] + tables_html + html[insert_pos:]
    html_path.write_text(new_html, encoding="utf-8")
    logger.info("appended %d CSV tables to HTML", len(csv_files))


def append_csv_tables_to_markdown(md_path: Path, csv_files: list):
    """Append CSV tables to the end of Markdown file."""
    md_content = md_path.read_text(encoding="utf-8")
    
    # Build tables section
    tables_md = '\n---\n\n## Extracted Tables (CSV)\n\n'
    
    for csv_path in csv_files:
        rel_path = os.path.relpath(csv_path, start=md_path.parent).replace("\\", "/")
        tables_md += f'### {csv_path.name}\n\n'
        tables_md += f'[Download CSV]({rel_path})\n\n'
        tables_md += csv_to_markdown_table(csv_path)
    
    # Append to end
    new_md = md_content + tables_md
    md_path.write_text(new_md, encoding="utf-8")
    logger.info("appended %d CSV tables to Markdown", len(csv_files))


def main():
    logger.info("starting parser")
    if not INPUT_PDF.exists():
        logger.error("input PDF not found: %s", INPUT_PDF.resolve())
        return

    # Create separate folders
    pages_dir = _ensure_images_dir(OUT_DIR, PAGES_SUBFOLDER)
    figures_dir = _ensure_images_dir(OUT_DIR, FIGURES_SUBFOLDER)
    tables_dir = _ensure_images_dir(OUT_DIR, TABLES_SUBFOLDER)
    csv_dir = _ensure_images_dir(OUT_DIR, CSV_SUBFOLDER)

    pdf_opts = PdfPipelineOptions()
    pdf_opts.images_scale = IMAGE_RESOLUTION_SCALE
    pdf_opts.generate_page_images = True
    pdf_opts.generate_picture_images = True

    format_options = {InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_opts)}
    converter = DocumentConverter(format_options=format_options)

    logger.info("converting %s ...", INPUT_PDF.name)
    conv_res = converter.convert(INPUT_PDF)
    doc = conv_res.document
    logger.info("conversion done. pages=%d", len(doc.pages))

    items = list(doc.iterate_items())
    pictures = [el for el, _ in items if isinstance(el, PictureItem)]
    tables = [el for el, _ in items if isinstance(el, TableItem)]
    logger.info("layout items=%d pictures=%d tables=%d", len(items), len(pictures), len(tables))

    # Save page images
    saved_pages = 0
    for page_no, page in doc.pages.items():
        if getattr(page, "image", None) is not None:
            dest = pages_dir / f"{INPUT_PDF.stem}-page-{page_no}.png"
            page.image.pil_image.save(dest, format="PNG")
            copied_images_cache[dest.resolve()] = f"{PAGES_SUBFOLDER}/{dest.name}"
            saved_pages += 1
    logger.info("saved %d page images", saved_pages)

    # Save pictures and tables separately
    pic_c = 0
    tab_c = 0
    for el, _ in items:
        if isinstance(el, PictureItem):
            pic_c += 1
            dest = figures_dir / f"{INPUT_PDF.stem}-picture-{pic_c}.png"
            img = el.get_image(doc)
            if img is not None:
                img.save(dest, "PNG")
                copied_images_cache[dest.resolve()] = f"{FIGURES_SUBFOLDER}/{dest.name}"

        if isinstance(el, TableItem):
            tab_c += 1
            dest = tables_dir / f"{INPUT_PDF.stem}-table-{tab_c}.png"
            img = el.get_image(doc)
            if img is not None:
                img.save(dest, "PNG")
                copied_images_cache[dest.resolve()] = f"{TABLES_SUBFOLDER}/{dest.name}"

    logger.info("saved %d pictures and %d tables", pic_c, tab_c)
    
        # Also export Docling-detected tables to CSV
    docling_csv_count = 0
    for table_ix, table in enumerate(tables, start=1):
        try:
            df = table.export_to_dataframe(doc)
            csv_path = csv_dir / f"{INPUT_PDF.stem}-docling-table-{table_ix}.csv"
            df.to_csv(csv_path, index=False)
            docling_csv_count += 1
            logger.info("saved Docling CSV table: %s", csv_path.name)
        except Exception as e:
            logger.error("error exporting Docling table %d: %s", table_ix, e)

    # Export markdown and HTML
    md_embedded = OUT_DIR / f"{INPUT_PDF.stem}-with-images-embedded.md"
    md_refs = OUT_DIR / f"{INPUT_PDF.stem}-with-image-refs.md"
    html_refs = OUT_DIR / f"{INPUT_PDF.stem}-with-image-refs.html"

    doc.save_as_markdown(md_embedded, image_mode=ImageRefMode.EMBEDDED)
    doc.save_as_markdown(md_refs, image_mode=ImageRefMode.REFERENCED)
    doc.save_as_html(html_refs, image_mode=ImageRefMode.REFERENCED)

    # Fix references
    _fix_html_image_refs(html_refs, OUT_DIR)
    _fix_markdown_image_refs(md_refs, OUT_DIR)

    # Extract tables with pdfplumber and save as CSV
    csv_files = extract_tables_with_pdfplumber(INPUT_PDF, csv_dir)

    # Append CSV tables to HTML and Markdown
    if csv_files:
        append_csv_tables_to_html(html_refs, csv_files)
        append_csv_tables_to_markdown(md_refs, csv_files)
        logger.info("CSV tables appended to outputs")

    logger.info("done. open %s in a browser to verify", html_refs)


if __name__ == "__main__":
    main()