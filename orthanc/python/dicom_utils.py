"""
DICOM Utilities - Handle DICOM operations with Orthanc
"""

import json
import logging
import tempfile
from pathlib import Path
from typing import Optional

try:
    import orthanc
    import pydicom
    from pydicom.errors import InvalidDicomError
    from PIL import Image
    import numpy as np
    ORTHANC_AVAILABLE = True
except ImportError:
    ORTHANC_AVAILABLE = False
    logging.warning("Required packages not available")


class DICOMUtils:
    """Utilities for DICOM processing with Orthanc"""
    
    def __init__(self):
        self.temp_dir = Path(tempfile.gettempdir()) / "orthanc-ilo-dicom"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
    
    def is_chest_xray(self, instance_id: str) -> bool:
        """
        Check if a DICOM instance is a chest X-ray
        
        Args:
            instance_id: Orthanc instance ID
        
        Returns:
            True if it's a chest X-ray, False otherwise
        """
        try:
            # Get DICOM tags from Orthanc
            tags_response = orthanc.RestApiGet(f'/instances/{instance_id}/simplified-tags')
            # Handle different response types (bytes, str, or dict)
            if isinstance(tags_response, bytes):
                tags = json.loads(tags_response.decode('utf-8'))
                #logging.warning(f"Tags response: {json.dumps(tags, indent=2)}")
            else:
                logging.warning(f"Unexpected tags response type: {type(tags_response)}")
                return False
            
            # Check Modality (should be CR, DX, or XR for X-rays)
            modality = tags.get('Modality', {}).upper()
            if modality not in ['CR', 'DX', 'XR']:
                return False
            
            # Check Body Part Examined (should include CHEST or THORAX)
            body_part = tags.get('BodyPartExamined', {}).upper()
            view_position = tags.get('ViewPosition', {}).upper()
            if 'CHEST' in body_part or 'THORAX' in body_part and view_position in ['PA', 'AP']:
                logging.warning(f"Instance {instance_id} is a chest X-ray")
                return True

            return False
        
        except Exception as e:
            logging.error(f"Error checking if instance is chest X-ray: {e}")
            return False
    
    def get_dicom_file(self, instance_id: str) -> str:
        """
        Get DICOM file from Orthanc instance
        
        Args:
            instance_id: Orthanc instance ID
        
        Returns:
            Path to DICOM file
        """
        try:
            # Get DICOM file from Orthanc
            dicom_data = orthanc.RestApiGet(f'/instances/{instance_id}/file')
            
            # Save to temp file
            dicom_path = self.temp_dir / f"{instance_id}.dcm"
            with open(dicom_path, 'wb') as f:
                f.write(dicom_data)
            
            logging.info(f"Saved DICOM file: {dicom_path}")
            return str(dicom_path)
        
        except Exception as e:
            logging.error(f"Error getting DICOM file: {e}")
            raise
    
    def extract_image(self, instance_id: str, output_format: str = 'PNG', max_size: Optional[int] = None) -> str:
        """
        Extract image from DICOM instance with optional resizing
        
        Args:
            instance_id: Orthanc instance ID
            output_format: Output image format (PNG, JPEG)
            max_size: Optional maximum side length (maintains aspect ratio). If None, no resizing.
        
        Returns:
            Path to extracted image file
        """
        if not ORTHANC_AVAILABLE:
            raise ImportError("Required packages (pydicom, PIL, numpy) are not available")
        
        try:
            # Get DICOM file from Orthanc
            dicom_data = orthanc.RestApiGet(f'/instances/{instance_id}/file')
            
            # Save to temp file
            dicom_path = self.temp_dir / f"{instance_id}.dcm"
            with open(dicom_path, 'wb') as f:
                f.write(dicom_data)
            
            # Load DICOM with pydicom
            ds = pydicom.dcmread(str(dicom_path))
            
            # Extract pixel array
            pixel_array = ds.pixel_array
            
            # Apply RescaleSlope and RescaleIntercept if present (for proper windowing)
            if hasattr(ds, 'RescaleSlope') and hasattr(ds, 'RescaleIntercept'):
                pixel_array = pixel_array * ds.RescaleSlope + ds.RescaleIntercept
            
            # Handle PhotometricInterpretation (MONOCHROME1 vs MONOCHROME2)
            photometric = getattr(ds, 'PhotometricInterpretation', 'MONOCHROME2')
            
            # MONOCHROME1: pixel values increase with increasing X-ray intensity (darker = higher)
            # MONOCHROME2: pixel values increase with decreasing X-ray intensity (brighter = higher) - standard
            if photometric == 'MONOCHROME1':
                # Invert: MONOCHROME1 needs to be inverted to match MONOCHROME2 display
                pixel_array = pixel_array.max() - pixel_array
                logging.debug(f"Inverted MONOCHROME1 image")
            elif photometric != 'MONOCHROME2':
                logging.warning(f"Unusual PhotometricInterpretation: {photometric}, treating as MONOCHROME2")
            
            # Normalize to 0-255
            if pixel_array.max() > 255 or pixel_array.min() < 0:
                # Normalize to 0-255 range
                pixel_array = ((pixel_array - pixel_array.min()) / 
                             (pixel_array.max() - pixel_array.min()) * 255).astype(np.uint8)
            else:
                pixel_array = pixel_array.astype(np.uint8)
            
            # Handle different bit depths and color spaces
            if len(pixel_array.shape) == 2:
                # Grayscale
                image = Image.fromarray(pixel_array, mode='L')
            elif len(pixel_array.shape) == 3:
                # RGB or color
                image = Image.fromarray(pixel_array, mode='RGB')
            else:
                raise ValueError(f"Unexpected image shape: {pixel_array.shape}")
            
            # Convert to RGB if grayscale (for consistency)
            if image.mode == 'L':
                image = image.convert('RGB')
            
            # Resize if max_size is specified
            if max_size is not None:
                original_size = image.size
                # Calculate new size maintaining aspect ratio
                if original_size[0] > original_size[1]:
                    # Width is larger
                    new_width = max_size
                    new_height = int(original_size[1] * (max_size / original_size[0]))
                else:
                    # Height is larger or equal
                    new_height = max_size
                    new_width = int(original_size[0] * (max_size / original_size[1]))
                
                image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
                logging.info(f"Resized image from {original_size} to {(new_width, new_height)} (max side: {max_size})")
            
            # Save image
            output_path = self.temp_dir / f"{instance_id}.{output_format.lower()}"
            image.save(str(output_path), format=output_format)
            
            logging.info(f"Extracted image: {output_path}")
            return str(output_path)
        
        except Exception as e:
            logging.error(f"Error extracting image from DICOM: {e}")
            raise
    
    def get_instance_info(self, instance_id: str) -> dict:
        """
        Get information about a DICOM instance
        
        Args:
            instance_id: Orthanc instance ID
        
        Returns:
            Dictionary with instance information including series_id and study_id (via ParentSeries)
        """
        try:
            # Get instance info from Orthanc (always returns JSON string)
            instance_json_str = orthanc.RestApiGet(f'/instances/{instance_id}')
            instance_json = json.loads(instance_json_str)
            
            # Get ParentSeries from instance
            parent_series_id = instance_json.get('ParentSeries')
            
            # Get ParentStudy from series (requires second API call)
            parent_study_id = None
            modality = ''
            series_description = ''
            
            if parent_series_id:
                try:
                    # Always returns JSON string
                    series_json_str = orthanc.RestApiGet(f'/series/{parent_series_id}')
                    series_json = json.loads(series_json_str)
                    
                    parent_study_id = series_json.get('ParentStudy')
                    main_tags = series_json.get('MainDicomTags', {})
                    modality = main_tags.get('Modality', '')
                    series_description = main_tags.get('SeriesDescription', '')
                except Exception as e:
                    logging.warning(f"Failed to get parent study from series {parent_series_id}: {e}")
            
            return {
                'instance_id': instance_id,
                'series_id': parent_series_id,
                'study_id': parent_study_id,
                'modality': modality,
                'series_description': series_description
            }
        except Exception as e:
            logging.error(f"Error getting instance info: {e}")
            import traceback
            logging.debug(traceback.format_exc())
            return {}

