#!/usr/bin/env python3
"""
PDF text extractor for old FCAT Promoció PDFs (2008-2009 era).

These PDFs store text in PostScript content streams with (string) encoding,
not in a layout-preserving format. This module decompresses FlateDecode streams
and extracts text from PostScript string literals.
"""

import zlib
import re


def extract_text_from_pdf(pdf_path):
    """Extract all text from a PDF by decompressing content streams.
    
    Returns a single text string with lines separated by newlines.
    """
    with open(pdf_path, 'rb') as f:
        data = f.read()
    
    # Find all FlateDecode streams
    pattern = rb'/Filter/FlateDecode.*?stream\r?\n(.*?)endstream'
    matches = re.findall(pattern, data, re.DOTALL)
    
    all_lines = []
    for stream in matches:
        try:
            decompressed = zlib.decompress(stream)
            text = decompressed.decode('latin-1', errors='replace')
            
            # Extract text between parentheses (PostScript string literals)
            strings = re.findall(r'\(([^)]*)\)', text)
            for s in strings:
                # Convert to printable ASCII
                printable = ''.join(c if 32 <= ord(c) < 127 else ' ' for c in s)
                stripped = printable.strip()
                if stripped:
                    all_lines.append(stripped)
        except Exception:
            pass
    
    return '\n'.join(all_lines)


def extract_text_with_position(pdf_path):
    """Extract text with approximate Y-position for layout reconstruction.
    
    Returns list of (y_position, text) tuples sorted top-to-bottom.
    """
    with open(pdf_path, 'rb') as f:
        data = f.read()
    
    pattern = rb'/Filter/FlateDecode.*?stream\r?\n(.*?)endstream'
    matches = re.findall(pattern, data, re.DOTALL)
    
    results = []
    for stream in matches:
        try:
            decompressed = zlib.decompress(stream)
            text = decompressed.decode('latin-1', errors='replace')
            
            # Find BT/ET blocks with text positioning
            # Pattern: x Y Td/Tm then (text) Tj
            for block_match in re.finditer(rb'BT(.*?)ET', stream, re.DOTALL):
                block = block_match.group(1).decode('latin-1', errors='replace')
                
                # Find position + text pairs
                # Format: X Y Td (text) Tj  or  X Y Tm (text) Tj
                for tj_match in re.finditer(
                    r'(\d+\.?\d*)\s+(\d+\.?\d*)\s+(?:Td|Tm)\s*\(([^)]*)\)\s*Tj',
                    block
                ):
                    y = float(tj_match.group(2))
                    text_str = tj_match.group(3)
                    printable = ''.join(c if 32 <= ord(c) < 127 else ' ' for c in text_str)
                    stripped = printable.strip()
                    if stripped:
                        results.append((y, stripped))
                
                # Also handle TJ operator: [(text1) (text2) ...] TJ
                for tj_match in re.finditer(
                    r'(\d+\.?\d*)\s+(\d+\.?\d*)\s+(?:Td|Tm)\s*\[(.*?)\]\s*TJ',
                    block
                ):
                    y = float(tj_match.group(2))
                    inner = tj_match.group(3)
                    # Extract individual strings from [...]
                    items = re.findall(r'\(([^)]*)\)', inner)
                    for item in items:
                        printable = ''.join(c if 32 <= ord(c) < 127 else ' ' for c in item)
                        stripped = printable.strip()
                        if stripped:
                            results.append((y, stripped))
        except Exception:
            pass
    
    # Sort by Y position (descending — PDFs start from top)
    results.sort(key=lambda x: -x[0])
    return results
