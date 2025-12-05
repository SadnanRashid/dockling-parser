import cv2
import pytesseract
import os
import numpy as np
import pandas as pd
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def check_tables_in_images(image_folder, output_folder):
    os.makedirs(output_folder, exist_ok=True)

    for filename in os.listdir(image_folder):
        if filename.lower().endswith((".png", ".jpg", ".jpeg", ".tiff", ".bmp")):
            image_path = os.path.join(image_folder, filename)
            image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)

            # Thresholding
            _, thresh = cv2.threshold(image, 128, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

            # Detect horizontal and vertical lines
            horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25,1))
            vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1,25))

            horizontal_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, horizontal_kernel)
            vertical_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, vertical_kernel)

            # Combine lines to detect table-like structures
            table_mask = cv2.add(horizontal_lines, vertical_lines)
            has_table = np.sum(table_mask) > 1000  # threshold for detecting lines

            print(f"{filename}: {'Yes' if has_table else 'No'}")

            if has_table:
                # Invert image back for OCR
                inv_image = cv2.bitwise_not(image)
                
                # Extract text with pytesseract (simple approach)
                custom_config = r'--oem 3 --psm 6'
                text = pytesseract.image_to_string(inv_image, config=custom_config)

                # Convert text to CSV (assuming tabular text with spaces)
                rows = [line.split() for line in text.split('\n') if line.strip()]
                if rows:
                    df = pd.DataFrame(rows)
                    csv_name = os.path.splitext(filename)[0] + ".csv"
                    df.to_csv(os.path.join(output_folder, csv_name), index=False, header=False)

if __name__ == "__main__":
    check_tables_in_images(
        r"C:\Users\HP\Downloads\dockling-parser\demo3\tables",
        r"C:\Users\HP\Downloads\dockling-parser\demo3\tables_output"
    )
