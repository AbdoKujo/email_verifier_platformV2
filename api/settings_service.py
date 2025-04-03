import os
import sys
import csv
import logging
from typing import Dict, List, Any, Optional

# Add parent directory to path to import models
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import models
from models.settings_model import SettingsModel

logger = logging.getLogger(__name__)

class SettingsService:
    """Service for handling application settings."""
    
    def __init__(self):
        """Initialize the settings service."""
        self.settings_model = SettingsModel()
    
    def get_all_settings(self) -> Dict[str, Any]:
        """
        Get all application settings.
        
        Returns:
            Dict[str, Any]: All application settings
        """
        try:
            # Load settings from the settings model
            self.settings_model.load_settings()
            
            # Convert settings to a more API-friendly format
            settings = {}
            for feature, data in self.settings_model.settings.items():
                settings[feature] = {
                    'value': data['value'],
                    'enabled': data['enabled']
                }
            
            return settings
        except Exception as e:
            logger.error(f"Error getting settings: {e}")
            return {'error': str(e)}
    
    def update_settings(self, settings_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update application settings.
        
        Args:
            settings_data: Dictionary of settings to update
            
        Returns:
            Dict[str, Any]: Result of the update operation
        """
        try:
            # Load current settings
            self.settings_model.load_settings()
            
            # Update settings
            for feature, data in settings_data.items():
                if isinstance(data, dict) and 'value' in data:
                    # If data is a dictionary with 'value' key
                    value = data['value']
                    enabled = data.get('enabled', True)
                    self.settings_model.set(feature, str(value), enabled)
                else:
                    # If data is just a value
                    self.settings_model.set(feature, str(data), True)
            
            # Save settings
            success = self.settings_model.save_settings()
            
            if success:
                return {
                    'success': True,
                    'message': 'Settings updated successfully',
                    'settings': self.get_all_settings()
                }
            else:
                return {
                    'success': False,
                    'message': 'Failed to save settings'
                }
        except Exception as e:
            logger.error(f"Error updating settings: {e}")
            return {
                'success': False,
                'message': f'Error updating settings: {str(e)}'
            }