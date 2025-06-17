#!/usr/bin/env python3
"""
Test script for document conversion functionality
"""

import os
import sys

def test_document_conversion():
    """Test the document conversion function"""
    print("Testing document conversion...")
    
    # Import the conversion function
    try:
        from media_util_gui import convert_document
        print("✓ Successfully imported convert_document function")
    except ImportError as e:
        print(f"✗ Failed to import convert_document: {e}")
        return False
    
    # Check for test files
    pdf_file = "1-The-Innovation-Spark-1.pdf"
    if not os.path.exists(pdf_file):
        print(f"✗ Test PDF file not found: {pdf_file}")
        return False
    
    print(f"✓ Found test PDF file: {pdf_file}")
    print(f"  File size: {os.path.getsize(pdf_file)} bytes")
    
    # Test PDF to Word conversion
    print("\n--- Testing PDF to Word conversion ---")
    try:
        result = convert_document(pdf_file, 'docx')
        print(f"Conversion function returned: {result}")
        
        # Check if output file was created
        output_file = "1-The-Innovation-Spark-1_converted.docx"
        if os.path.exists(output_file):
            print(f"✓ Success! Created: {output_file}")
            print(f"  Output file size: {os.path.getsize(output_file)} bytes")
            return True
        else:
            print("✗ Error: Output file was not created")
            return False
            
    except Exception as e:
        print(f"✗ Error during conversion: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_document_conversion()
    if success:
        print("\n🎉 Document conversion test PASSED!")
    else:
        print("\n❌ Document conversion test FAILED!")
    
    sys.exit(0 if success else 1)
