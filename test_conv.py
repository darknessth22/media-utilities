import os
import sys

# Try to import fitz, maybe it's under PyMuPDF?
try:
    import fitz
    print("fitz imported successfully.")
    
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50,50), 'Phase 4 Test Heading', fontsize=20)
    page.insert_text((50,100), 'This is a test paragraph with bold.', fontsize=12)
    doc.save('test_phase4.pdf')

    from core.document import convert_document
    success, msg, summary = convert_document('test_phase4.pdf', 'docx')
    print("Conversion success:", success)
    print("Message:", msg)
    if summary:
        print("Summary Headings:", summary.headings)
        print("Summary Text Blocks:", summary.text_blocks)
except ImportError:
    print("Could not import fitz in this environment.")
