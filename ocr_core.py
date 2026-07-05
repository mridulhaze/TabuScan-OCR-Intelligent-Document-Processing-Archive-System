import easyocr
import re
import os
from PIL import Image
import numpy as np


# Initialize EasyOCR reader
_reader = None

def get_reader():
    global _reader
    if _reader is None:
        print("Initializing EasyOCR reader for Bengali and English...")
        _reader = easyocr.Reader(['bn', 'en'], verbose=False)
    return _reader

# Bengali to English digit translation map
bengali_to_english = {
    '০': '0', '১': '1', '২': '2', '৩': '3', '৪': '4',
    '৫': '5', '৬': '6', '৭': '7', '৮': '8', '৯': '9'
}

# Mapping common character misrecognitions in registration and roll numbers
char_map = {
    'H': '4', 'E': '4', 'L': '1', 'I': '1', '|': '1',
    '[': '1', ']': '1', '{': '1', '}': '1', '!': '1',
    '(': '1', 't': '1', 'd': '0', 'o': '0', 'O': '0',
    's': '8', 'S': '5', 'g': '9', 'y': '4', 'a': '9',
    'b': '6', 'q': '9', 'i': '1', ';': '', ':': '',
    '_': '', '-': '', ',': '', ' ': '', "'": '', '"': '',
    '#': '', 'ড': '7', 'প': '7', 'হ': '1', 'ম': '3',
    'ং': '0', 'ঢ': '9', 'ী': '0', 'দ': '0'
}

def clean_digits(text):
    if not text:
        return ""
    # Convert Bengali digits
    converted = ""
    for char in text:
        if char in bengali_to_english:
            converted += bengali_to_english[char]
        else:
            converted += char
            
    # Apply char mapping
    mapped = ""
    for char in converted:
        if char in char_map:
            mapped += char_map[char]
        elif char.isdigit():
            mapped += char
            
    # Filter to keep only digits
    digits_only = re.sub(r"\D", "", mapped)
    return digits_only

def process_tabulation_image(image_path):
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found at: {image_path}")
        
    reader = get_reader()
    print(f"Running cropped OCR on: {image_path}")
    
    # Load image and crop to the left 250 pixels (contains Roll & Reg columns)
    img = Image.open(image_path)
    cropped_img = img.crop((0, 0, 250, img.height))
    cropped_numpy = np.array(cropped_img)
    
    results = reader.readtext(cropped_numpy)
    print(f"OCR complete. Found {len(results)} text blocks in cropped view.")
    
    # Sort and cluster into rows based on Y coordinate
    sorted_boxes = []
    for entry in results:
        bbox, text, conf = entry
        
        xs = [pt[0] for pt in bbox]
        ys = [pt[1] for pt in bbox]
        cx = sum(xs) / len(xs)
        cy = sum(ys) / len(ys)
        
        sorted_boxes.append({
            "text": text,
            "cx": cx,
            "cy": cy,
            "bbox": bbox
        })
        
    sorted_boxes.sort(key=lambda x: x["cy"])
    
    # Only keep boxes in student table area (vertical coordinates between 250 and 1200)
    student_boxes = [b for b in sorted_boxes if 250 < b["cy"] < 1200]
    
    # Cluster boxes into rows (Y coordinate difference < 25)
    rows = []
    for b in student_boxes:
        found_row = False
        for r in rows:
            mean_cy = sum(item["cy"] for item in r) / len(r)
            if abs(b["cy"] - mean_cy) < 25:
                r.append(b)
                found_row = True
                break
        if not found_row:
            rows.append([b])
            
    # Filter rows that look like actual student table rows
    # In a cropped view, a student row must be inside the table Y-range and have at least 1 item
    valid_rows = []
    for r in rows:
        mean_cy = sum(item["cy"] for item in r) / len(r)
        if 250 < mean_cy < 1180 and len(r) >= 1:
            valid_rows.append(r)
            
    # Sort the rows from top to bottom
    valid_rows.sort(key=lambda r: sum(item["cy"] for item in r)/len(r))
    
    parsed_students = []
    
    for idx, r in enumerate(valid_rows):
        r.sort(key=lambda x: x["cx"])
        
        # Roll candidate: leftmost text (cx < 100)
        roll_items = [item for item in r if item["cx"] < 100]
        # Reg candidate: second column (100 <= cx < 200)
        reg_items = [item for item in r if 100 <= item["cx"] < 200]
        
        raw_roll = roll_items[0]["text"] if roll_items else ""
        raw_reg = ""
        
        # Take the most promising registration text block
        if reg_items:
            # Sort by cx to find the one closest to x=130 (reg column center)
            reg_items.sort(key=lambda x: abs(x["cx"] - 130))
            raw_reg = reg_items[0]["text"]
            
        cleaned_roll = clean_digits(raw_roll)
        cleaned_reg = clean_digits(raw_reg)
        
        # Limit to 5 digits for roll
        if cleaned_roll:
            cleaned_roll = cleaned_roll[:5]
            
        # Limit to 5 digits for registration
        if cleaned_reg:
            cleaned_reg = cleaned_reg[:5]
            
        parsed_students.append({
            "row_index": idx + 1,
            "raw_roll": raw_roll,
            "cleaned_roll": cleaned_roll,
            "raw_reg": raw_reg,
            "cleaned_reg": cleaned_reg
        })
        
    return parsed_students

# Eager-initialize the reader when the module is imported
get_reader()
