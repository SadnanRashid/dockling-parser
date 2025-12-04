import pdfplumber
import pandas as pd
import os

def extract_tables_from_pdf(pdf_path, output_folder="tables_output"):
    os.makedirs(output_folder, exist_ok=True)
    pdf = pdfplumber.open(pdf_path)
    table_count = 0
    for page_num, page in enumerate(pdf.pages, start=1):
        table = page.extract_table()

        if table:
            table_count += 1
            csv_path = os.path.join(output_folder, f"table_page{page_num}.csv")
            df = pd.DataFrame(table)
            df.to_csv(csv_path, index=False)

    pdf.close()

if __name__ == "__main__":
    extract_tables_from_pdf("imagetable.pdf")
