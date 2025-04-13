import os
import sys
import json
import time
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

# Add parent directory to path to import models
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import models
from models.bounce_model import BounceModel
from models.settings_model import SettingsModel
from models.common import VALID, INVALID, RISKY, CUSTOM

logger = logging.getLogger(__name__)

class BounceService:
    """Service for handling bounce verification."""
    
    def __init__(self):
        """Initialize the bounce service."""
        self.settings_model = SettingsModel()
        self.bounce_model = BounceModel(self.settings_model)
        self.results_dir = "./results"
        
        # Ensure directories exist
        os.makedirs(self.results_dir, exist_ok=True)
    
    def initiate_bounce_verification(self, emails: List[str], existing_batch_id: str = None) -> Dict[str, Any]:
        """
        Initiate bounce verification for a list of emails.
        
        Args:
            emails: List of email addresses to verify
            existing_batch_id: Optional existing batch ID to use
            
        Returns:
            Dict[str, Any]: Response with batch ID and estimated completion time
        """
        try:
            # Generate batch ID if not provided
            batch_id = existing_batch_id
            if not batch_id:
                batch_id = f"bounce_{int(time.time())}_{os.urandom(4).hex()}"
            
            # Start bounce verification in background (non-blocking)
            # This will just send the emails and return immediately
            self.bounce_model.batch_verify_emails_parallel(emails, batch_id)
            
            # Calculate estimated completion time
            # Assume 1 minute for initial sending + 30 minutes for bounce backs
            now = datetime.now()
            estimated_completion = now + timedelta(minutes=30)
            
            # Return response with batch ID and estimated completion time
            return {
                "header": f"Batch ID: {batch_id}",
                "batch_id": batch_id,
                "status": "initiated",
                "message": f"Bounce verification initiated for {len(emails)} emails",
                "total_emails": len(emails),
                "estimated_completion": estimated_completion.strftime("%Y-%m-%d %H:%M:%S"),
                "check_results_endpoint": f"/api/results/bounce/{batch_id}"
            }
        
        except Exception as e:
            logger.error(f"Error initiating bounce verification: {e}")
            return {
                "error": "Failed to initiate bounce verification",
                "details": str(e)
            }
    
    def check_bounce_verification(self, batch_id: str) -> Dict[str, Any]:
        """
        Check the status of a bounce verification batch.
        
        Args:
            batch_id: The batch ID to check
            
        Returns:
            Dict[str, Any]: Status of the bounce verification
        """
        try:
            # Determine the correct status file path
            status_file = None
            
            # Check in main results directory
            main_status_file = os.path.join(self.results_dir, batch_id, "status_b.json")
            if os.path.exists(main_status_file):
                status_file = main_status_file
            
            # Check in bounce_results directory
            bounce_status_file = os.path.join(self.results_dir, "bounce_results", batch_id, "status_b.json")
            if os.path.exists(bounce_status_file):
                status_file = bounce_status_file
            
            if not status_file:
                return {
                    "header": f"Batch ID: {batch_id}",
                    "batch_id": batch_id,
                    "status": "not_found",
                    "message": f"No bounce verification found for batch ID {batch_id}"
                }
            
            # Read status file
            with open(status_file, 'r', encoding='utf-8') as f:
                status_data = json.load(f)
            
            # Calculate progress
            total_emails = status_data.get("total_emails", 0)
            valid_count = status_data.get("valid", 0)
            invalid_count = status_data.get("invalid", 0)
            risky_count = status_data.get("risky", 0)
            custom_count = status_data.get("custom", 0)
            pending_count = status_data.get("pending", 0)
            
            processed_count = valid_count + invalid_count
            progress_percentage = 0
            if total_emails > 0:
                progress_percentage = (processed_count / total_emails) * 100
            
            # Determine if verification is complete
            is_complete = status_data.get("status") == "checked" and status_data.get("checking_attempts", 0) >= 3
            
            # Calculate remaining time
            remaining_time = "Unknown"
            if not is_complete:
                checking_attempts = status_data.get("checking_attempts", 0)
                if checking_attempts == 0:
                    remaining_time = "~30 minutes"
                elif checking_attempts == 1:
                    remaining_time = "~20 minutes"
                elif checking_attempts == 2:
                    remaining_time = "~10 minutes"
            
            # Return status
            return {
                "header": f"Batch ID: {batch_id}",
                "batch_id": batch_id,
                "status": status_data.get("status", "unknown"),
                "is_complete": is_complete,
                "total_emails": total_emails,
                "valid": valid_count,
                "invalid": invalid_count,
                "risky": risky_count,
                "custom": custom_count,
                "pending": pending_count,
                "progress_percentage": progress_percentage,
                "checking_attempts": status_data.get("checking_attempts", 0),
                "last_checked": status_data.get("last_checked", ""),
                "first_checked": status_data.get("first_checked", ""),
                "remaining_time": remaining_time
            }
        
        except Exception as e:
            logger.error(f"Error checking bounce verification status: {e}")
            return {
                "header": f"Batch ID: {batch_id}",
                "batch_id": batch_id,
                "status": "error",
                "message": f"Error checking bounce verification status: {str(e)}"
            }
    
    def process_bounce_responses(self, batch_id: str) -> Dict[str, Any]:
        """
        Process bounce responses for a verification batch.
        
        Args:
            batch_id: The batch ID
            
        Returns:
            Dict[str, Any]: Results of processing bounce responses
        """
        try:
            # Process responses
            invalid_emails, valid_emails = self.bounce_model.process_responses_parallel(batch_id, save_results=True)
            
            # Return results
            return {
                "header": f"Batch ID: {batch_id}",
                "batch_id": batch_id,
                "status": "processed",
                "message": f"Processed bounce responses for batch ID {batch_id}",
                "invalid_count": len(invalid_emails),
                "valid_count": len(valid_emails),
                "total_processed": len(invalid_emails) + len(valid_emails)
            }
        
        except Exception as e:
            logger.error(f"Error processing bounce responses: {e}")
            return {
                "header": f"Batch ID: {batch_id}",
                "batch_id": batch_id,
                "status": "error",
                "message": f"Error processing bounce responses: {str(e)}"
            }
