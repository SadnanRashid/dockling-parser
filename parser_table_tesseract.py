# image_parser.py
import cv2
import pytesseract
import numpy as np
import pandas as pd
from pathlib import Path

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
def detect_tables_from_image(image_path: Path, out_csv_dir: Path):
    image = cv2.imread(str(image_path))
    if image is None:
        return []

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)

    # 1. THRESHOLD
    thresh = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 15, 4
    )

    # 2. DETECT HORIZONTAL LINES
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
    detect_horizontal = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, horizontal_kernel)

    # 3. DETECT VERTICAL LINES
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
    detect_vertical = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, vertical_kernel)

    # 4. COMBINE TO FIND TABLE STRUCTURE
    table_mask = cv2.addWeighted(detect_horizontal, 0.5, detect_vertical, 0.5, 0)

    # 5. FIND CONTOURS OF TABLES
    contours, _ = cv2.findContours(table_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    csv_paths = []
    table_id = 1

    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)

        # Ignore very small detections
        if w < 100 or h < 100:
            continue

        # Crop table region
        table_roi = image[y:y + h, x:x + w]

        # OCR
        ocr_text = pytesseract.image_to_string(table_roi)

        # Convert OCR result → DataFrame
        rows = [r.split() for r in ocr_text.strip().split("\n") if r.strip()]
        if len(rows) == 0:
            continue

        df = pd.DataFrame(rows)

        # Save CSV
        out_csv_dir.mkdir(parents=True, exist_ok=True)
        csv_path = out_csv_dir / f"{image_path.stem}-table-{table_id}.csv"
        df.to_csv(csv_path, index=False, header=False)

        csv_paths.append(csv_path)
        table_id += 1

    return csv_paths


def process_all_images(images_folder: Path, out_csv_dir: Path):
    """
    Iterates through all PNG/JPG images in a folder and extracts tables.
    Returns dict: {image_path: [csv_list]}
    """
    results = {}

    for img_path in images_folder.glob("*.*"):
        if img_path.suffix.lower() not in [".png", ".jpg", ".jpeg"]:
            continue

        tables = detect_tables_from_image(img_path, out_csv_dir)
        results[img_path] = tables

    return results


if __name__ == "__main__":
    images_dir = Path("imagetable/images")   # your images folder from parser.py output
    output_dir = Path("imagetable/extracted_tables")

    res = process_all_images(images_dir, output_dir)

    print("Extraction complete.\n")
    for img, csvs in res.items():
        print(f"{img}:")
        for c in csvs:
            print("   →", c)
