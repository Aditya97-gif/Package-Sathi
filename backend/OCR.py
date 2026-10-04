import os
import sys
import json
import re
import cv2
import pytesseract

# Optional EasyOCR integration (for deep learning scene-text recognition)
try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False


# ==========================================
# 1. Image Preprocessing Pipelines (OpenCV)
# ==========================================

def get_greyscale_image(image):
    """Convert BGR image to single-channel Grayscale."""
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

def get_threshold_image(image):
    """Adaptive thresholding (superior to Otsu on reflective/glossy packaging)."""
    if len(image.shape) == 3:
        image = get_greyscale_image(image)
    return cv2.adaptiveThreshold(
        image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 4
    )

def remove_noise(image, diameter=9, sigma_color=75, sigma_space=75):
    """Edge-preserving bilateral filter: removes sensor/texture noise without blurring text edges."""
    return cv2.bilateralFilter(image, d=diameter, sigmaColor=sigma_color, sigmaSpace=sigma_space)

def enhance_contrast(image, clip_limit=2.0, tile_grid_size=(8, 8)):
    """CLAHE: Balances contrast on packaging images with shadows or glare."""
    if len(image.shape) == 3:
        image = get_greyscale_image(image)
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid_size)
    return clahe.apply(image)

def upscale_if_needed(image, target_max_dim=1800):
    """Upscale low-resolution images so small regulatory text reaches ~30-35px height."""
    h, w = image.shape[:2]
    max_dim = max(h, w)
    if max_dim < target_max_dim:
        scale = target_max_dim / max_dim
        return cv2.resize(image, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)
    return image

def preprocess_for_ocr(image):
    """
    Recommended end-to-end preprocessing pipeline for packaged commodity labels.
    Returns:
        gray_enhanced: Grayscale + CLAHE + Bilateral filter (best for dark text on light background)
        inverted: Bitwise not (best for light text on dark badges/headers)
    """
    # 1. Ensure sufficient resolution
    image = upscale_if_needed(image)
    
    # 2. Grayscale
    gray = get_greyscale_image(image)
    
    # 3. Denoise with edge preservation
    denoised = remove_noise(gray)
    
    # 4. Enhance contrast with CLAHE
    gray_enhanced = enhance_contrast(denoised)
    
    # 5. Inverted polarity for light text on dark backgrounds
    inverted = cv2.bitwise_not(gray_enhanced)
    
    return gray_enhanced, inverted


# ==========================================
# 2. OCR Engine Wrappers
# ==========================================

def ocr_core(img, config=r'--oem 3 --psm 11'):
    """
    Run Tesseract OCR.
    PSM 11 (Sparse text) is ideal for packaging labels with scattered badges and small print.
    """
    return pytesseract.image_to_string(img, config=config)

def run_multipass_tesseract(image):
    """
    Runs dual-polarity Tesseract passes and combines detected lines
    to capture both dark-on-light and light-on-dark label text.
    """
    normal, inverted = preprocess_for_ocr(image)
    
    # Pass 1: Normal polarity (PSM 11 - sparse text)
    text_normal = ocr_core(normal, config=r'--oem 3 --psm 11')
    
    # Pass 2: Layout block mode (PSM 4 - single column of variable text sizes)
    text_layout = ocr_core(normal, config=r'--oem 3 --psm 4')
    
    # Pass 3: Inverted polarity (for reverse-printed text on dark badges)
    text_inverted = ocr_core(inverted, config=r'--oem 3 --psm 11')
    
    # Merge and deduplicate lines while preserving order
    combined_lines = []
    seen = set()
    for text_block in [text_layout, text_normal, text_inverted]:
        for line in text_block.splitlines():
            clean = line.strip()
            if clean and len(clean) > 2 and clean not in seen:
                seen.add(clean)
                combined_lines.append(clean)
                
    return "\n".join(combined_lines)

def run_easyocr(image_or_path):
    """
    Run EasyOCR deep-learning text detection (CRAFT) and recognition (CRNN).
    Excels on curved bags, wrinkles, and stylized fonts.
    """
    if not EASYOCR_AVAILABLE:
        raise RuntimeError("EasyOCR is not installed. Run: pip install easyocr")
    reader = easyocr.Reader(['en'], gpu=False)
    results = reader.readtext(image_or_path, detail=0)
    return "\n".join(results)


# ==========================================
# 3. Legal Metrology Compliance Field Parser
# ==========================================

def extract_compliance_fields(text):
    """
    Extracts mandatory declarations as required by the
    Legal Metrology (Packaged Commodities) Rules, 2011:
    - MRP (Maximum Retail Price)
    - Net Quantity
    - Manufacturing / Packaging Date (MFD / PKD)
    - Expiry / Best Before / Use By Date
    - FSSAI License Number
    - Consumer Care Contact (Phone / Email)
    - Batch / Lot Number
    """
    fields = {
        "mrp": None,
        "net_quantity": None,
        "mfg_date": None,
        "expiry_date": None,
        "batch_number": None,
        "fssai_license": None,
        "consumer_helpline": None,
        "consumer_email": None
    }
    
    # 1. MRP (e.g., 'MRP Rs. 20.00', 'MRP : % 150.00', '₹ 50', 'M.R.P. : 120.00')
    mrp_match = re.search(
        r'(?:MRP|M\.R\.P\.)[^\d\n]{0,15}[:\.\-]?\s*[\₹\%\*Rs\.]*\s*(\d+(?:\.\d{1,2})?)',
        text, re.IGNORECASE
    )
    if mrp_match:
        fields["mrp"] = mrp_match.group(1)
        
    # 2. Net Quantity (e.g., 'Net Quantity: 1 Number', 'Net Qty: 20 g', '75g', '500 ml')
    net_match = re.search(
        r'(?:Net\s*(?:Quantity|Qty|Wt\.?|Weight|ary)|SERVE\s*SIZE)\s*[:\.\-]?\s*\n?\s*(\d+(?:\.\d+)?\s*(?:g|kg|ml|l|gm|grams|Number|N|u)\b)',
        text, re.IGNORECASE
    )
    if net_match:
        fields["net_quantity"] = net_match.group(1)
        
    # 3. Manufacturing Date (MFD / PKD / Month & Year of Manufacture e.g. 05-2025)
    mfd_match = re.search(
        r'(?:Month\s*&\s*Year\s*of\s*(?:Manufacture|Mfg)|MFD|PKD|MFR|Mfg\s*Date|Packed)\s*[:\.\-]?\s*\n?\s*([0-9]{2}[-\/\.][0-9]{4}|[0-9]{1,2}[-\/\.][0-9]{1,2}[-\/\.][0-9]{2,4}|[A-Za-z]{3}[-\s]\d{2,4})',
        text, re.IGNORECASE
    )
    if not mfd_match:
        # Standalone Month-Year format like 05-2025
        mfd_match = re.search(r'\b(0[1-9]|1[0-2])[-/](20\d{2})\b', text)
    if mfd_match:
        fields["mfg_date"] = mfd_match.group(0).strip()
        
    # 4. Expiry / Best Before / Use By / Shelf Life
    exp_match = re.search(
        r'(?:USE\s*BY|EXP(?:IRY)?(?:\s*DATE)?|BEST\s*BEFORE)\s*[:\.\-]?\s*\n?\s*([0-9]{1,2}[-\/\.][0-9]{1,2}[-\/\.][0-9]{2,4}|[A-Za-z]{3}[-\s]\d{2,4}|\d+\s*months?)',
        text, re.IGNORECASE
    )
    if not exp_match:
        # e.g., 'Four Months from manufacture' or '6 Months from packaging'
        exp_match = re.search(
            r'(\b(?:One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|Eleven|Twelve|\d+)\s*Months?\s*(?:from\s*(?:manufacture|pkd|mfd|packaging))?)',
            text, re.IGNORECASE
        )
    if exp_match:
        fields["expiry_date"] = exp_match.group(1).strip()
        
    # 5. Batch / Lot Number
    batch_match = re.search(
        r'(?:B\.?\s*NO|BATCH\s*(?:NO)?|LOT\s*(?:NO)?)\s*[:\.\-]?\s*([A-Za-z0-9\/\-]+)',
        text, re.IGNORECASE
    )
    if batch_match and len(batch_match.group(1)) > 1:
        fields["batch_number"] = batch_match.group(1)
        
    # 6. FSSAI License Number (14 digits)
    fssai_match = re.search(r'(?:fssai|Lic\s*(?:No|Number)\.?|Uc\s*No\.?)[^\d]{0,10}(\d{14})', text, re.IGNORECASE)
    if fssai_match:
        fields["fssai_license"] = fssai_match.group(1)
        
    # 7. Consumer Care Helpline (Toll free / Call / Tel)
    phone_match = re.search(
        r'(?:call|tel|toll[- ]free|phone|helpline)\s*(?:us\s*at)?\s*[:\.\-]?\s*([0-9\s]{8,18})',
        text, re.IGNORECASE
    )
    if not phone_match:
        # Check for '(Toll Free)' after number e.g. '000 800 050 7777 (Toll Free)'
        phone_match = re.search(r'([0-9\s]{8,18})\s*\(?Toll\s*Free\)?', text, re.IGNORECASE)
    if phone_match:
        fields["consumer_helpline"] = phone_match.group(1).strip()
        
    # 8. Consumer Care Email
    email_match = re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', text)
    if email_match:
        fields["consumer_email"] = email_match.group(0)
        
    return fields


# ==========================================
# 4. Main Execution
# ==========================================

def resolve_image_path(path):
    """Finds image relative to CWD or project root."""
    if os.path.exists(path):
        return path
    alt = os.path.join(os.path.dirname(__file__), '..', path)
    if os.path.exists(alt):
        return alt
    labels_alt = os.path.join(os.path.dirname(__file__), '..', 'labels', os.path.basename(path))
    if os.path.exists(labels_alt):
        return labels_alt
    return path


if __name__ == '__main__':
    # Parse CLI arguments: python OCR.py [image_path] [--engine tesseract|easyocr]
    img_arg = 'labels/Lays.jpg'
    engine = 'tesseract'
    
    for arg in sys.argv[1:]:
        if arg.startswith('--engine='):
            engine = arg.split('=', 1)[1].lower()
        elif arg == '--easyocr':
            engine = 'easyocr'
        elif not arg.startswith('-'):
            img_arg = arg
            
    resolved_path = resolve_image_path(img_arg)
    img = cv2.imread(resolved_path)
    if img is None:
        raise FileNotFoundError(f"Could not load image from '{resolved_path}'")
        
    print(f"=== Processing '{os.path.basename(resolved_path)}' with engine '{engine}' ===")
    
    if engine == 'easyocr' and EASYOCR_AVAILABLE:
        extracted_text = run_easyocr(resolved_path)
    else:
        extracted_text = run_multipass_tesseract(img)
        
    print("\n--- Extracted OCR Text ---")
    print(extracted_text)
    
    compliance_data = extract_compliance_fields(extracted_text)
    print("\n--- Legal Metrology Extracted Fields ---")
    print(json.dumps(compliance_data, indent=2))