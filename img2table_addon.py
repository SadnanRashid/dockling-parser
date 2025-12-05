from img2table.document import Image
from img2table.ocr import EasyOCR
import os

input_folder = r"C:\Users\HP\Downloads\dockling-parser\demo3\tables"
output_folder = r"C:\Users\HP\Downloads\dockling-parser\demo3\tables_output"
os.makedirs(output_folder, exist_ok=True)

# Instantiate EasyOCR (English language)
ocr = EasyOCR(lang=["en"])

# Process all images
for filename in os.listdir(input_folder):
    if filename.lower().endswith((".png", ".jpg", ".jpeg", ".tiff", ".bmp")):
        image_path = os.path.join(input_folder, filename)
        doc = Image(image_path, detect_rotation=False)
        
        # Extract tables
        tables = doc.extract_tables(ocr=ocr,
                                    implicit_rows=False,
                                    implicit_columns=False,
                                    borderless_tables=False,
                                    min_confidence=50)
        
        # Save each table as CSV
        for i, table in enumerate(tables):
            csv_name = f"{os.path.splitext(filename)[0]}_table{i+1}.csv"
            table.df.to_csv(os.path.join(output_folder, csv_name), index=False)
        
        print(f"{filename}: {len(tables)} table(s) extracted")
