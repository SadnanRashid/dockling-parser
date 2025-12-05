import warnings
warnings.filterwarnings("ignore", category=UserWarning)

import pdfplumber
import pandas as pd
import os

def extract_tables_from_pdf(pdf_path, output_folder="tables_output"):
    os.makedirs(output_folder, exist_ok=True)
    pdf = pdfplumber.open(pdf_path)
    for page_num, page in enumerate(pdf.pages, start=1):
        tables = page.extract_tables()
        for idx, table in enumerate(tables, start=1):
            print(f"Page {page_num}: {idx} table(s) extracted")
            csv_path = os.path.join(output_folder, f"table_page{page_num}_{idx}.csv")
            pd.DataFrame(table).to_csv(csv_path, index=False)
    pdf.close()

extract_tables_from_pdf("imagetable.pdf")
