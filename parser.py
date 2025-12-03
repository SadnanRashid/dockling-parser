# parser.py
import logging
import os
import re
import shutil
import urllib.parse
from pathlib import Path

from docling_core.types.doc import ImageRefMode, PictureItem, TableItem
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

INPUT_PDF = Path("demo.pdf")
OUT_DIR = Path("scratch")
IMAGES_SUBFOLDER = "images"
OUT_DIR.mkdir(parents=True, exist_ok=True)
IMAGE_RESOLUTION_SCALE = 2.0

logger = logging.getLogger("parser")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def _ensure_images_dir(out_dir: Path, subfolder: str = IMAGES_SUBFOLDER) -> Path:
    p = out_dir / subfolder
    p.mkdir(parents=True, exist_ok=True)
    return p


def _copy_into_images(found: Path, out_dir: Path, images_dir: Path) -> str:
    dest = images_dir / found.name
    i = 1
    while dest.exists():
        dest = images_dir / f"{found.stem}_{i}{found.suffix}"
        i += 1
    shutil.copy2(found, dest)
    return os.path.relpath(dest, start=out_dir).replace("\\", "/")


def _fix_html_image_refs(html_path: Path, out_dir: Path, images_subfolder: str = IMAGES_SUBFOLDER):
    html = html_path.read_text(encoding="utf-8")
    html = urllib.parse.unquote(html)
    images_dir = _ensure_images_dir(out_dir, images_subfolder)
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
            except Exception:
                pass
        if not found:
            name = Path(decoded).name
            for p in out_dir.rglob(name):
                found = p.resolve()
                break
        if not found:
            return f'src="{decoded}"'
        try:
            found.relative_to(out_dir)
            rel = os.path.relpath(found, start=out_dir).replace("\\", "/")
            return f'src="{rel}"'
        except Exception:
            rel = _copy_into_images(found, out_dir, images_dir)
            return f'src="{rel}"'

    fixed = src_re.sub(repl, html)
    html_path.write_text(fixed, encoding="utf-8")
    return html_path


def _fix_markdown_image_refs(md_path: Path, out_dir: Path, images_subfolder: str = IMAGES_SUBFOLDER):
    text = md_path.read_text(encoding="utf-8")
    images_dir = _ensure_images_dir(out_dir, images_subfolder)
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
        try:
            found.relative_to(out_dir)
            rel = os.path.relpath(found, start=out_dir).replace("\\", "/")
        except Exception:
            rel = _copy_into_images(found, out_dir, images_dir)
        return f'![{alt}]({rel})'

    fixed = md_img_re.sub(repl, text)
    md_path.write_text(fixed, encoding="utf-8")
    return md_path


def main():
    logger.info("starting parser")
    if not INPUT_PDF.exists():
        logger.error("input PDF not found: %s", INPUT_PDF.resolve())
        return

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

    # save page images
    saved_pages = 0
    for page_no, page in doc.pages.items():
        if getattr(page, "image", None) is not None:
            out_page = OUT_DIR / f"{INPUT_PDF.stem}-page-{page_no}.png"
            page.image.pil_image.save(out_page, format="PNG")
            saved_pages += 1
            logger.info("saved page image: %s", out_page)
    logger.info("saved %d page images", saved_pages)

    # save picture/table images
    pic_c = 0
    tab_c = 0
    for el, _ in items:
        if isinstance(el, PictureItem):
            pic_c += 1
            out_pic = OUT_DIR / f"{INPUT_PDF.stem}-picture-{pic_c}.png"
            img = el.get_image(doc)
            if img is not None:
                img.save(out_pic, format="PNG")
                logger.info("saved picture image: %s", out_pic)
        if isinstance(el, TableItem):
            tab_c += 1
            out_table = OUT_DIR / f"{INPUT_PDF.stem}-table-{tab_c}.png"
            img = el.get_image(doc)
            if img is not None:
                img.save(out_table, format="PNG")
                logger.info("saved table image: %s", out_table)
    logger.info("saved %d pictures and %d tables", pic_c, tab_c)

    md_embedded = OUT_DIR / f"{INPUT_PDF.stem}-with-images-embedded.md"
    md_refs = OUT_DIR / f"{INPUT_PDF.stem}-with-image-refs.md"
    html_refs = OUT_DIR / f"{INPUT_PDF.stem}-with-image-refs.html"

    doc.save_as_markdown(md_embedded, image_mode=ImageRefMode.EMBEDDED)
    logger.info("saved embedded markdown: %s", md_embedded)

    doc.save_as_markdown(md_refs, image_mode=ImageRefMode.REFERENCED)
    logger.info("saved markdown refs: %s", md_refs)

    doc.save_as_html(html_refs, image_mode=ImageRefMode.REFERENCED)
    logger.info("saved html refs: %s", html_refs)

    logger.info("fixing html image refs")
    _fix_html_image_refs(html_refs, OUT_DIR, IMAGES_SUBFOLDER)
    logger.info("fixing markdown image refs")
    _fix_markdown_image_refs(md_refs, OUT_DIR, IMAGES_SUBFOLDER)

    logger.info("done. open %s in a browser to verify", html_refs)


if __name__ == "__main__":
    main()
