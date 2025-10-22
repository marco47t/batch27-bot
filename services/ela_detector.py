# services/ela_detector.py
from PIL import Image, ImageChops, ImageEnhance
import numpy as np
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

def perform_ela(image_path: str, quality: int = 90) -> Dict[str, Any]:
    """
    Perform Error Level Analysis to detect image tampering with region analysis
    Edited areas will have different compression levels
    """
    try:
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
        max_diff = max([ex for ex in extrema])[1]
        
        # Convert to numpy for analysis
        ela_array = np.array(ela_image)
        mean_diff = np.mean(ela_array)
        std_diff = np.std(ela_array)
        
        # Analyze regions to find suspicious areas
        suspicious_regions = analyze_suspicious_regions(ela_array, original.size)
        
        # Clean up temp file
        import os
        if os.path.exists(temp_path):
            os.remove(temp_path)
        
        # Analyze results
        is_suspicious = False
        risk_score = 0
        reasons = []
        
        if max_diff > 20:
            is_suspicious = True
            risk_score += 3
            reasons.append(f"High compression variance detected (max: {max_diff})")
        
        if std_diff > 15:
            is_suspicious = True
            risk_score += 2
            reasons.append(f"Inconsistent compression patterns (std: {std_diff:.2f})")
        
        if suspicious_regions:
            is_suspicious = True
            risk_score += min(len(suspicious_regions), 3)
            reasons.append(f"Found {len(suspicious_regions)} suspicious region(s)")
        
        # Calculate risk level
        if risk_score >= 4:
            risk_level = "HIGH"
        elif risk_score >= 2:
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
            "message": "; ".join(reasons) if reasons else "Compression levels consistent"
        }
        
    except Exception as e:
        logger.error(f"ELA analysis failed: {e}")
        return {
            "is_suspicious": False,
            "risk_level": "UNKNOWN",
            "suspicious_regions": [],
            "message": f"ELA analysis error: {str(e)}"
        }


def analyze_suspicious_regions(ela_array: np.ndarray, image_size: tuple) -> List[str]:
    """
    Analyze ELA array to identify specific regions with high error levels
    Returns human-readable descriptions of suspicious areas
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
    threshold = overall_mean * 1.5  # 50% higher than average = suspicious
    
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
            
            # Check if region is suspicious
            if region_mean > threshold and region_max > 25:
                region_name = region_names[row][col]
                suspicious_regions.append(
                    f"{region_name} (error: {region_mean:.1f}, max: {region_max})"
                )
    
    return suspicious_regions
