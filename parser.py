import logging
import os
import re
import shutil
import urllib.parse
import warnings
from pathlib import Path

import pandas as pd
from docling_core.types.doc import ImageRefMode, PictureItem, TableItem
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

warnings.filterwarnings("ignore", category=UserWarning)

INPUT_PDF = Path("Semester-VII.pdf")
OUT_DIR = Path("Semester-VII")

# Subfolders
PAGES_SUBFOLDER = "pages"
FIGURES_SUBFOLDER = "figures"
TABLES_SUBFOLDER = "tables"
CSV_SUBFOLDER = "extracted_csv"  

OUT_DIR.mkdir(parents=True, exist_ok=True)
IMAGE_RESOLUTION_SCALE = 2.0

logger = logging.getLogger("parser")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

copied_images_cache = {}


def _ensure_images_dir(out_dir: Path, subfolder: str) -> Path:
    p = out_dir / subfolder
    p.mkdir(parents=True, exist_ok=True)
    return p


def _copy_into_images(found: Path, out_dir: Path, images_dir: Path) -> str:
    fpath = found.resolve()
    if fpath in copied_images_cache:
        return copied_images_cache[fpath]

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


# ---------- MAIN ----------

def main():
    logger.info("starting parser")
    if not INPUT_PDF.exists():
        logger.error("input PDF not found: %s", INPUT_PDF.resolve())
        return

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

    # Save pages
    saved_pages = 0
    for page_no, page in doc.pages.items():
        if getattr(page, "image", None) is not None:
            dest = pages_dir / f"{INPUT_PDF.stem}-page-{page_no}.png"
            page.image.pil_image.save(dest, format="PNG")
            copied_images_cache[dest.resolve()] = f"{PAGES_SUBFOLDER}/{dest.name}"
            saved_pages += 1
    logger.info("saved %d page images", saved_pages)

    # Save pictures and tables
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

    # Save Docling tables as CSV
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

    # Export markdown + html
    md_refs = OUT_DIR / f"{INPUT_PDF.stem}-with-image-refs.md"
    html_refs = OUT_DIR / f"{INPUT_PDF.stem}-with-image-refs.html"

    doc.save_as_markdown(md_refs, image_mode=ImageRefMode.REFERENCED)
    doc.save_as_html(html_refs, image_mode=ImageRefMode.REFERENCED)

    _fix_markdown_image_refs(md_refs, OUT_DIR)
    _fix_html_image_refs(html_refs, OUT_DIR)

    logger.info("done. open %s in a browser to verify", html_refs)


if __name__ == "__main__":
    main()
