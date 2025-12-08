import fitz  # PyMuPDF

def flatten_pdf_form(input_pdf, output_pdf, font_size=10):
    """
    Flatten AcroForm PDF: draw form field values directly onto the page,
    remove interactive widgets, and save as a normal PDF.

    Args:
        input_pdf (str): Path to original PDF.
        output_pdf (str): Path to flattened PDF.
        font_size (int): Text size for overlay writing.
    """
    doc = fitz.open(input_pdf)

    for page in doc:
        widgets = page.widgets()
        if not widgets:
            continue

        for widget in widgets:
            rect = widget.rect
            value = widget.field_value

            if value:
                # Draw the text into the PDF directly
                page.insert_textbox(
                    rect,
                    str(value),
                    fontsize=font_size,
                    color=(0, 0, 0),
                    fontname="helv"
                )

            # Remove widget (field)
            widget.update(visible=False)

    # Save final flattened PDF
    doc.save(output_pdf, deflate=True)
    print(f"Flattened PDF saved to: {output_pdf}")


render_pdf_with_form_fields(
    input_pdf="Sample-Fillable-PDF-filled.pdf",
    output_image_folder="Sample-Fillable-PDF-flat.pdf",
    zoom=2.0
)
