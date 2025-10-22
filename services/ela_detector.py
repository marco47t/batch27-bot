# services/ela_detector.py
from PIL import Image, ImageChops, ImageEnhance
import numpy as np
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

def is_screenshot_or_low_quality(image_path: str) -> bool:
    """Detect if image is a screenshot or low quality (common for receipts)"""
    try:
        img = Image.open(image_path)
        
        # Check for no EXIF (typical of screenshots)
        exif = img._getexif()
        if not exif:
            return True
        
        # Check image size - very large images are unlikely to be screenshots
        width, height = img.size
        if width > 2000 or height > 2000:
            return False
            
        # Check aspect ratio - screenshots often have phone aspect ratios
        aspect = max(width, height) / min(width, height)
        if 1.5 <= aspect <= 2.5:  # Common phone ratios
            return True
            
        return False
    except:
        return True  # Assume screenshot on error


def perform_ela(image_path: str, quality: int = 90) -> Dict[str, Any]:
    """
    Perform Error Level Analysis to detect image tampering
    OPTIMIZED for screenshots and low-quality images (common for receipts)
    """
    try:
        # Check if screenshot/low quality first
        is_screenshot = is_screenshot_or_low_quality(image_path)
        
        # Open original image
        original = Image.open(image_path)
        
        # Convert to RGB if needed
        if original.mode != 'RGB':
            original = original.convert('RGB')
        
        # Save at specified quality
        temp_path = image_path + "_ela_temp.jpg"
        original.save(temp_path, 'JPEG', quality=quality)
        
        # Reopen compressed version
        compressed = Image.open(temp_path)
        
        # Calculate difference
        ela_image = ImageChops.difference(original, compressed)
        
        # Get extrema to check for tampering
        extrema = ela_image.getextrema()
        max_diff = max([ex[1] for ex in extrema])
        
        # Convert to numpy for analysis
        ela_array = np.array(ela_image)
        mean_diff = np.mean(ela_array)
        std_diff = np.std(ela_array)
        
        # Analyze regions to find suspicious areas
        suspicious_regions = analyze_suspicious_regions(ela_array, original.size, is_screenshot)
        
        # Clean up temp file
        import os
        if os.path.exists(temp_path):
            os.remove(temp_path)
        
        # ADJUSTED THRESHOLDS for screenshots and low-quality images
        if is_screenshot:
            # Much more lenient for screenshots
            max_diff_threshold = 40  # Increased from 20
            std_threshold = 25       # Increased from 15
            region_threshold = 3      # Only flag if 3+ regions
        else:
            # Normal thresholds for regular photos
            max_diff_threshold = 25
            std_threshold = 18
            region_threshold = 2
        
        # Analyze results
        is_suspicious = False
        risk_score = 0
        reasons = []
        
        if max_diff > max_diff_threshold:
            is_suspicious = True
            risk_score += 3
            reasons.append(f"High compression variance detected (max: {max_diff})")
        
        if std_diff > std_threshold:
            is_suspicious = True
            risk_score += 2
            reasons.append(f"Inconsistent compression patterns (std: {std_diff:.2f})")
        
        if len(suspicious_regions) >= region_threshold:
            is_suspicious = True
            risk_score += min(len(suspicious_regions), 3)
            reasons.append(f"Found {len(suspicious_regions)} suspicious region(s)")
        
        # IMPORTANT: Reduce score if screenshot (screenshots naturally have artifacts)
        if is_screenshot and risk_score > 0:
            original_score = risk_score
            risk_score = max(0, risk_score - 2)  # Reduce by 2 points
            logger.info(f"Screenshot detected - ELA score reduced from {original_score} to {risk_score}")
        
        # Calculate risk level
        if risk_score >= 5:
            risk_level = "HIGH"
        elif risk_score >= 3:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"
        
        return {
            "is_suspicious": is_suspicious,
            "risk_level": risk_level,
            "max_difference": max_diff,
            "mean_difference": mean_diff,
            "std_deviation": std_diff,
            "risk_score": risk_score,
            "reasons": reasons,
            "suspicious_regions": suspicious_regions,
            "is_screenshot": is_screenshot,
            "message": "; ".join(reasons) if reasons else "Compression levels consistent"
        }
        
    except Exception as e:
        logger.error(f"ELA analysis failed: {e}")
        return {
            "is_suspicious": False,
            "risk_level": "UNKNOWN",
            "suspicious_regions": [],
            "is_screenshot": True,
            "message": f"ELA analysis error: {str(e)}"
        }


def analyze_suspicious_regions(ela_array: np.ndarray, image_size: tuple, is_screenshot: bool) -> List[str]:
    """
    Analyze ELA array to identify specific regions with high error levels
    ADJUSTED for screenshots
    """
    suspicious_regions = []
    height, width = ela_array.shape[:2]
    
    # Divide image into grid (3x3)
    grid_h = height // 3
    grid_w = width // 3
    
    # Region names
    region_names = [
        ["Top-left", "Top-center", "Top-right"],
        ["Middle-left", "Center", "Middle-right"],
        ["Bottom-left", "Bottom-center", "Bottom-right"]
    ]
    
    # Analyze each region
    overall_mean = np.mean(ela_array)
    
    # ADJUSTED: More lenient threshold for screenshots
    if is_screenshot:
        threshold = overall_mean * 2.0  # 100% higher than average (was 1.5x)
        max_threshold = 40               # Increased from 25
    else:
        threshold = overall_mean * 1.5
        max_threshold = 25
    
    for row in range(3):
        for col in range(3):
            # Extract region
            y_start = row * grid_h
            y_end = (row + 1) * grid_h if row < 2 else height
            x_start = col * grid_w
            x_end = (col + 1) * grid_w if col < 2 else width
            
            region = ela_array[y_start:y_end, x_start:x_end]
            region_mean = np.mean(region)
            region_max = np.max(region)
            
            # Check if region is suspicious (stricter criteria)
            if region_mean > threshold and region_max > max_threshold:
                region_name = region_names[row][col]
                suspicious_regions.append(
                    f"{region_name} (error: {region_mean:.1f}, max: {region_max})"
                )
    
    return suspicious_regions
