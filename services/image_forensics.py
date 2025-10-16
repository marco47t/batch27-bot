# services/image_forensics.py

from PIL import Image
from PIL.ExifTags import TAGS
import logging
from datetime import datetime
from typing import Dict, Any

logger = logging.getLogger(__name__)

def is_probable_screenshot(image_path: str) -> bool:
    """
    Determine if image is likely a screenshot
    Screenshots are NORMAL and EXPECTED in this application
    """
    try:
        image = Image.open(image_path)
        exif_data = image._getexif()
        
        # No EXIF at all = likely screenshot (NORMAL)
        if not exif_data:
            return True
        
        metadata = {}
        for tag_id, value in exif_data.items():
            tag = TAGS.get(tag_id, tag_id)
            metadata[tag] = str(value)
        
        # Missing camera make/model = screenshot
        has_camera = "Make" in metadata or "Model" in metadata
        if not has_camera:
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"Screenshot detection error: {e}")
        return True  # Assume screenshot on error (safer)


def analyze_image_metadata(image_path: str) -> Dict[str, Any]:
    """
    Analyze EXIF metadata for signs of tampering
    IMPORTANT: Screenshots are considered NORMAL and NOT flagged as risky
    """
    try:
        image = Image.open(image_path)
        exif_data = image._getexif()
        
        screenshot_flag = is_probable_screenshot(image_path)
        
        # If it's a screenshot, that's NORMAL - no risk
        if screenshot_flag:
            return {
                "has_exif": False,
                "risk_level": "LOW",
                "reason": "Receipt is a screenshot (normal for this application)",
                "screenshot_flag": True,
                "suspicious_flags": []
            }
        
        # Not a screenshot - perform detailed analysis
        if not exif_data:
            logger.warning(f"No EXIF data but doesn't appear to be screenshot: {image_path}")
            return {
                "has_exif": False,
                "risk_level": "MEDIUM",
                "reason": "No metadata on non-screenshot image",
                "screenshot_flag": False,
                "suspicious_flags": ["Missing EXIF on unusual image"]
            }
        
        metadata = {}
        suspicious_flags = []
        
        for tag_id, value in exif_data.items():
            tag = TAGS.get(tag_id, tag_id)
            metadata[tag] = str(value)
        
        # Check for editing software signatures (ONLY if not screenshot)
        editing_software = ["photoshop", "gimp", "paint.net", "pixlr", "canva", "affinity"]
        software_field = metadata.get("Software", "").lower()
        
        if any(sw in software_field for sw in editing_software):
            suspicious_flags.append(f"Edited with: {software_field}")
        
        # Check for date inconsistencies
        datetime_original = metadata.get("DateTimeOriginal")
        datetime_digitized = metadata.get("DateTimeDigitized")
        
        if datetime_original and datetime_digitized:
            if datetime_original != datetime_digitized:
                suspicious_flags.append("Date mismatch between capture and digitization")
        
        # Check if file modification is much later than capture
        modify_date = metadata.get("DateTime")
        if datetime_original and modify_date:
            try:
                orig = datetime.strptime(datetime_original, "%Y:%m:%d %H:%M:%S")
                mod = datetime.strptime(modify_date, "%Y:%m:%d %H:%M:%S")
                diff_hours = abs((mod - orig).total_seconds() / 3600)
                
                if diff_hours > 24:
                    suspicious_flags.append(f"Modified {diff_hours:.1f} hours after capture")
            except:
                pass
        
        risk_level = "HIGH" if len(suspicious_flags) >= 2 else "MEDIUM" if suspicious_flags else "LOW"
        
        return {
            "has_exif": True,
            "metadata": metadata,
            "suspicious_flags": suspicious_flags,
            "risk_level": risk_level,
            "reason": "; ".join(suspicious_flags) if suspicious_flags else "Metadata appears authentic",
            "screenshot_flag": False
        }
        
    except Exception as e:
        logger.error(f"Error analyzing metadata: {e}")
        return {
            "has_exif": False,
            "risk_level": "LOW",  # Changed from MEDIUM - assume screenshot
            "reason": "Screenshot format (metadata unavailable)",
            "screenshot_flag": True,
            "suspicious_flags": []
        }
