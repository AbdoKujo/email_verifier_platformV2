import os
import sys
import json
import logging
from typing import Dict, List, Any, Optional

# Add parent directory to path to import models
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import models
from models.statistics_model import StatisticsModel
from models.settings_model import SettingsModel
from models.common import VALID, INVALID, RISKY, CUSTOM

logger = logging.getLogger(__name__)

class StatisticsService:
    """Service for handling verification statistics."""
    
    def __init__(self):
        """Initialize the statistics service."""
        self.settings_model = SettingsModel()
        self.statistics_model = StatisticsModel(self.settings_model)
        self.statistics_dir = "./statistics"
        self.history_dir = os.path.join(self.statistics_dir, "history")
        
        # Ensure directories exist
        os.makedirs(self.statistics_dir, exist_ok=True)
        os.makedirs(self.history_dir, exist_ok=True)
    
    def get_global_statistics(self) -> Dict[str, Any]:
        """
        Get global verification statistics.
        
        Returns:
            Dict[str, Any]: Global verification statistics
        """
        try:
            # Get statistics from the statistics model
            statistics = self.statistics_model.get_statistics()
            
            # Convert to a more API-friendly format
            return {
                'timestamp': statistics.get('timestamp', ''),
                'categories': {
                    VALID: statistics.get(VALID, {}).get('total', 0),
                    INVALID: statistics.get(INVALID, {}).get('total', 0),
                    RISKY: statistics.get(RISKY, {}).get('total', 0),
                    CUSTOM: statistics.get(CUSTOM, {}).get('total', 0)
                },
                'total_emails': sum(statistics.get(cat, {}).get('total', 0) for cat in [VALID, INVALID, RISKY, CUSTOM]),
                'domains': statistics.get('domains', {}),
                'reasons': {
                    VALID: statistics.get(VALID, {}).get('reasons', {}),
                    INVALID: statistics.get(INVALID, {}).get('reasons', {}),
                    RISKY: statistics.get(RISKY, {}).get('reasons', {}),
                    CUSTOM: statistics.get(CUSTOM, {}).get('reasons', {})
                }
            }
        except Exception as e:
            logger.error(f"Error getting global statistics: {e}")
            return {
                'error': str(e),
                'categories': {
                    VALID: 0,
                    INVALID: 0,
                    RISKY: 0,
                    CUSTOM: 0
                },
                'total_emails': 0,
                'domains': {},
                'reasons': {}
            }
    
    def get_email_history(self, email: str) -> Optional[Dict[str, Any]]:
        """
        Get verification history for a specific email.
        
        Args:
            email: The email address
            
        Returns:
            Optional[Dict[str, Any]]: The verification history, or None if not found
        """
        try:
            # Get history from the statistics model
            history = self.statistics_model.get_verification_history(email=email)
            
            if not history:
                return None
            
            return history
        except Exception as e:
            logger.error(f"Error getting history for email {email}: {e}")
            return None
    
    def get_category_history(self, category: str) -> Optional[Dict[str, Any]]:
        """
        Get verification history filtered by category.
        
        Args:
            category: The category (valid, invalid, risky, custom)
            
        Returns:
            Optional[Dict[str, Any]]: The verification history, or None if not found
        """
        try:
            # Validate category
            if category.lower() not in [VALID, INVALID, RISKY, CUSTOM]:
                return None
            
            # Get history from the statistics model
            history = self.statistics_model.get_verification_history(category=category.lower())
            
            if not history:
                return None
            
            return history
        except Exception as e:
            logger.error(f"Error getting history for category {category}: {e}")
            return None