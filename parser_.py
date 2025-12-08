# parser.py
import logging
import os
import re
import shutil
import urllib.parse
from pathlib import Path
from typing import Optional, Tuple, Set

from docling_core.types.doc import ImageRefMode, PictureItem, TableItem
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

INPUT_PDF = Path("demo2.pdf")
OUT_DIR = Path("scratch")
IMAGES_SUBFOLDER = "images"
OUT_DIR.mkdir(parents=True, exist_ok=True)
IMAGE_RESOLUTION_SCALE = 2.0

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("parser")


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


def _fix_html_image_refs(html_path: Path, out_dir: Path, images_subfolder: str = IMAGES_SUBFOLDER) -> Path:
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


def _fix_markdown_image_refs(md_path: Path, out_dir: Path, images_subfolder: str = IMAGES_SUBFOLDER) -> Path:
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


def _get_bbox(el) -> Optional[Tuple[float, float, float, float]]:
    bbox = getattr(el, "bbox", None)
    if bbox is not None:
        x = getattr(bbox, "x", None) or getattr(bbox, "left", None)
        y = getattr(bbox, "y", None) or getattr(bbox, "top", None)
        w = getattr(bbox, "w", None) or getattr(bbox, "width", None)
        h = getattr(bbox, "h", None) or getattr(bbox, "height", None)
        if None not in (x, y, w, h):
            return (x, y, x + w, y + h)
        left = getattr(bbox, "left", None)
        top = getattr(bbox, "top", None)
        right = getattr(bbox, "right", None)
        bottom = getattr(bbox, "bottom", None)
        if None not in (left, top, right, bottom):
            return (left, top, right, bottom)
    x = getattr(el, "x", None) or getattr(el, "left", None)
    y = getattr(el, "y", None) or getattr(el, "top", None)
    w = getattr(el, "w", None) or getattr(el, "width", None)
    h = getattr(el, "h", None) or getattr(el, "height", None)
    if None not in (x, y, w, h):
        return (x, y, x + w, y + h)
    return None


def _iou(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    if inter_x1 >= inter_x2 or inter_y1 >= inter_y2:
        return 0.0
    inter = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
    a_area = max(0.0, (ax2 - ax1)) * max(0.0, (ay2 - ay1))
    b_area = max(0.0, (bx2 - bx1)) * max(0.0, (by2 - by1))
    union = a_area + b_area - inter
    if union <= 0:
        return 0.0
    return inter / union


def _remove_table_image_refs_from_html(html_path: Path, table_basenames: Set[str]) -> None:
    text = html_path.read_text(encoding="utf-8")
    # remove <figure>..</figure> if it contains an <img src="...basename...">
    def figure_filter(match):
        block = match.group(0)
        for name in table_basenames:
            if name in block:
                return ""  # drop the whole figure
        return block

    fixed = re.sub(r"<figure.*?>.*?</figure>", figure_filter, text, flags=re.DOTALL | re.IGNORECASE)
    # also remove standalone <img ...> tags referencing table images
    for name in table_basenames:
        fixed = re.sub(rf'<img[^>]*{re.escape(name)}[^>]*>', '', fixed)
    html_path.write_text(fixed, encoding="utf-8")


def _remove_table_image_refs_from_md(md_path: Path, table_basenames: Set[str]) -> None:
    text = md_path.read_text(encoding="utf-8")
    # remove markdown image references that point to a table image
    def md_filter(match):
        url = match.group(2)
        decoded = urllib.parse.unquote(url).replace("\\", "/")
        if Path(decoded).name in table_basenames:
            return ""  # drop image token
        return match.group(0)

    fixed = re.sub(r'!\[([^\]]*)\]\((.*?)\)', md_filter, text)
    md_path.write_text(fixed, encoding="utf-8")


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
    tables = [el for el, _ in items if isinstance(el, TableItem)]
    pictures = [el for el, _ in items if isinstance(el, PictureItem)]
    logger.info("layout items=%d pictures=%d tables=%d", len(items), len(pictures), len(tables))

    saved_pages = 0
    for page_no, page in doc.pages.items():
        if getattr(page, "image", None) is not None:
            out_page = OUT_DIR / f"{INPUT_PDF.stem}-page-{page_no}.png"
            page.image.pil_image.save(out_page, format="PNG")
            saved_pages += 1
            logger.info("saved page image: %s", out_page)
    logger.info("saved %d page images", saved_pages)

    table_bboxes = []
    table_image_paths = []
    for idx, tbl in enumerate(tables, start=1):
        tb = _get_bbox(tbl)
        if tb is not None:
            table_bboxes.append(tb)
        out_table = OUT_DIR / f"{INPUT_PDF.stem}-table-{idx}.png"
        img = tbl.get_image(doc)
        if img is not None:
            img.save(out_table, format="PNG")
            table_image_paths.append(out_table)
            logger.info("saved table image: %s", out_table)

    images_dir = _ensure_images_dir(OUT_DIR, IMAGES_SUBFOLDER)
    IOU_THRESHOLD = 0.30
    OVERLAP_AREA_RATIO = 0.5
    MIN_PIC_AREA_TO_CHECK = 200

    pic_count = 0
    saved_pic_paths = []

    for idx, (el, _ctx) in enumerate(items, start=1):
        if not isinstance(el, PictureItem):
            continue
        pb = _get_bbox(el)
        save_picture = True
        if pb is not None:
            pic_area = max(0.0, (pb[2] - pb[0])) * max(0.0, (pb[3] - pb[1]))
            if pic_area >= MIN_PIC_AREA_TO_CHECK and table_bboxes:
                for tb in table_bboxes:
                    iou_val = _iou(pb, tb)
                    if iou_val >= IOU_THRESHOLD:
                        ix1 = max(pb[0], tb[0])
                        iy1 = max(pb[1], tb[1])
                        ix2 = min(pb[2], tb[2])
                        iy2 = min(pb[3], tb[3])
                        if ix1 < ix2 and iy1 < iy2:
                            inter_area = (ix2 - ix1) * (iy2 - iy1)
                            if (inter_area / float(pic_area)) >= OVERLAP_AREA_RATIO:
                                save_picture = False
                                break
        if not save_picture:
            continue
        pic_count += 1
        out_pic = images_dir / f"{INPUT_PDF.stem}-picture-{pic_count}.png"
        img = el.get_image(doc)
        if img is not None:
            img.save(out_pic, format="PNG")
            saved_pic_paths.append(out_pic)
            logger.info("saved picture image: %s", out_pic)

    logger.info("saved %d pictures", len(saved_pic_paths))

    md_embedded = OUT_DIR / f"{INPUT_PDF.stem}-with-images-embedded.md"
    md_refs = OUT_DIR / f"{INPUT_PDF.stem}-with-image-refs.md"
    html_refs = OUT_DIR / f"{INPUT_PDF.stem}-with-image-refs.html"

    doc.save_as_markdown(md_embedded, image_mode=ImageRefMode.EMBEDDED)
    logger.info("saved embedded markdown: %s", md_embedded)

    doc.save_as_markdown(md_refs, image_mode=ImageRefMode.REFERENCED)
    logger.info("saved markdown refs: %s", md_refs)

    doc.save_as_html(html_refs, image_mode=ImageRefMode.REFERENCED)
    logger.info("saved html refs: %s", html_refs)

    # remove references to images that correspond to table crops
    table_basenames = {p.name for p in table_image_paths}
    if table_basenames:
        logger.info("removing table image references from outputs")
        _remove_table_image_refs_from_html(html_refs, table_basenames)
        _remove_table_image_refs_from_md(md_refs, table_basenames)

    # normalize remaining image references and copy assets into images/
    logger.info("fixing html image refs")
    _fix_html_image_refs(html_refs, OUT_DIR, IMAGES_SUBFOLDER)
    logger.info("fixing markdown image refs")
    _fix_markdown_image_refs(md_refs, OUT_DIR, IMAGES_SUBFOLDER)

    logger.info("done. open %s in a browser to verify", html_refs)


if __name__ == "__main__":
    main()
