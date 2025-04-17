import os
import sys
import json
import csv
import logging
from typing import Dict, List, Any, Optional

# Add parent directory to path to import models
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import models
from models.common import VALID, INVALID, RISKY, CUSTOM

logger = logging.getLogger(__name__)

class ResultsService:
    """Service for handling verification results."""
    
    def __init__(self):
        """Initialize the results service."""
        self.results_dir = "./results"
        self.data_dir = "./data"
        
        # Ensure directories exist
        os.makedirs(self.results_dir, exist_ok=True)
        os.makedirs(self.data_dir, exist_ok=True)
    
    def get_all_results(self) -> Dict[str, Any]:
        """
        Get all verification results.
        
        Returns:
            Dict[str, Any]: All verification results
        """
        # Get results from data files
        data_results = self._get_data_results()
        
        # Get results from job directories
        job_results = self._get_job_results()
        
        # Combine results
        return {
            'data_results': data_results,
            'job_results': job_results
        }
    
    def _get_data_results(self) -> Dict[str, Any]:
        """
        Get results from data files.
        
        Returns:
            Dict[str, Any]: Results from data files
        """
        results = {}
        
        # Get results for each category
        for category in [VALID, INVALID, RISKY, CUSTOM]:
            # Check data file
            data_file = os.path.join(self.data_dir, f"{category.capitalize()}.csv")
            if os.path.exists(data_file):
                results[category] = self._read_csv_file(data_file)
            else:
                results[category] = []
            
            # Check results file
            results_file = os.path.join(self.results_dir, f"{category}_Results.csv")
            if os.path.exists(results_file):
                results[f"{category}_details"] = self._read_csv_file(results_file)
            else:
                results[f"{category}_details"] = []
        
        return results
    
    def _get_job_results(self) -> Dict[str, Any]:
        """
        Get results from job directories.
        
        Returns:
            Dict[str, Any]: Results from job directories
        """
        job_results = {}
        
        # Get all job directories
        try:
            for item in os.listdir(self.results_dir):
                job_dir = os.path.join(self.results_dir, item)
                
                # Check if it's a directory
                if os.path.isdir(job_dir):
                    # Check if status file exists
                    status_file = os.path.join(job_dir, "status.json")
                    if os.path.exists(status_file):
                        try:
                            with open(status_file, 'r', encoding='utf-8') as f:
                                job_status = json.load(f)
                                
                                # Add job status to results
                                job_results[item] = job_status
                                
                                # Add simplified results if available
                                emails_results_file = os.path.join(job_dir, "emails_results.csv")
                                if os.path.exists(emails_results_file):
                                    job_results[item]['simplified_results'] = self._read_csv_file(emails_results_file)
                                else:
                                    # Add detailed results if simplified not available
                                    job_results[item]['detailed_results'] = self._get_job_detailed_results(item)
                        except Exception as e:
                            logger.error(f"Error loading job status for {item}: {e}")
        except Exception as e:
            logger.error(f"Error getting job results: {e}")
        
        return job_results
    
    def _get_job_detailed_results(self, job_id: str) -> Dict[str, Any]:
        """
        Get detailed results for a specific job.
        
        Args:
            job_id: Unique identifier for the verification job
            
        Returns:
            Dict[str, Any]: Detailed results for the job
        """
        detailed_results = {}
        
        # Get results for each category
        for category in [VALID, INVALID, RISKY, CUSTOM]:
            results_file = os.path.join(self.results_dir, job_id, f"{category}_Results.csv")
            if os.path.exists(results_file):
                detailed_results[category] = self._read_csv_file(results_file)
            else:
                detailed_results[category] = []
        
        return detailed_results
    
    def get_job_results(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get verification results for a specific job.
        
        Args:
            job_id: Unique identifier for the verification job
            
        Returns:
            Optional[Dict[str, Any]]: The job results, or None if not found
        """
        job_dir = os.path.join(self.results_dir, job_id)
        
        # Check if job directory exists
        if not os.path.isdir(job_dir):
            return None
        
        # Check if status file exists
        status_file = os.path.join(job_dir, "status.json")
        if not os.path.exists(status_file):
            return None
        
        try:
            # Load job status
            with open(status_file, 'r', encoding='utf-8') as f:
                job_status = json.load(f)
            
            # Check for simplified results first
            emails_results_file = os.path.join(job_dir, "emails_results.csv")
            if os.path.exists(emails_results_file):
                # Return simplified results (email, status, provider)
                simplified_results = self._read_csv_file(emails_results_file)
                
                # Convert to a more convenient format
                results_by_email = {}
                for result in simplified_results:
                    if 'Email' in result and 'Status' in result:
                        email = result['Email']
                        status = result['Status']
                        provider = result.get('Provider', 'unknown')
                        results_by_email[email] = {
                            'status': status,
                            'provider': provider
                        }
                
                job_status['simplified_results'] = results_by_email
            else:
                # Fall back to detailed results
                job_status['detailed_results'] = self._get_job_detailed_results(job_id)
            
            return job_status
        except Exception as e:
            logger.error(f"Error getting job results for {job_id}: {e}")
            return None
    
    def _read_csv_file(self, file_path: str) -> List[Dict[str, str]]:
        """
        Read a CSV file and return its contents as a list of dictionaries.
        
        Args:
            file_path: Path to the CSV file
            
        Returns:
            List[Dict[str, str]]: Contents of the CSV file
        """
        results = []
        
        try:
            with open(file_path, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    results.append(dict(row))
        except Exception as e:
            logger.error(f"Error reading CSV file {file_path}: {e}")
        
        return results

    def get_bounce_results(self) -> Dict[str, Any]:
        """
        Get all bounce verification results.
        
        Returns:
            Dict[str, Any]: All bounce verification results
        """
        bounce_results = {}
        
        try:
            # Check bounce_results directory
            bounce_results_dir = os.path.join(self.results_dir, "bounce_results")
            if (os.path.exists(bounce_results_dir)):
                for item in os.listdir(bounce_results_dir):
                    item_path = os.path.join(bounce_results_dir, item)
                    if os.path.isdir(item_path) and item.startswith("bounce_"):
                        batch_id = item
                        
                        # Get batch status
                        status_file = os.path.join(item_path, "status_b.json")
                        if os.path.exists(status_file):
                            try:
                                with open(status_file, 'r', encoding='utf-8') as f:
                                    status_data = json.load(f)
                                    bounce_results[batch_id] = status_data
                            except Exception as e:
                                logger.error(f"Error reading status file for {batch_id}: {e}")
            
            # Also check main results directory for bounce verifications
            if os.path.exists(self.results_dir):
                for item in os.listdir(self.results_dir):
                    item_path = os.path.join(self.results_dir, item)
                    if os.path.isdir(item_path):
                        status_b_file = os.path.join(item_path, "status_b.json")
                        if os.path.exists(status_b_file):
                            try:
                                with open(status_b_file, 'r', encoding='utf-8') as f:
                                    status_data = json.load(f)
                                    bounce_results[item] = status_data
                            except Exception as e:
                                logger.error(f"Error reading status file for {item}: {e}")
        
        except Exception as e:
            logger.error(f"Error getting bounce results: {e}")
        
        return bounce_results
    
    def get_bounce_batch_results(self, batch_id: str) -> Optional[Dict[str, Any]]:
        """
        Get bounce verification results for a specific batch.
        
        Args:
            batch_id: The batch ID
            
        Returns:
            Optional[Dict[str, Any]]: The batch results, or None if not found
        """
        # Check in main results directory
        status_file = os.path.join(self.results_dir, batch_id, "status_b.json")
        if os.path.exists(status_file):
            try:
                with open(status_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error reading status file for {batch_id}: {e}")
        
        # Check in bounce_results directory
        bounce_status_file = os.path.join(self.results_dir, "bounce_results", batch_id, "status_b.json")
        if os.path.exists(bounce_status_file):
            try:
                with open(bounce_status_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error reading status file for {batch_id}: {e}")
        
        return None

    def get_batch_ids(self) -> List[str]:
        """
        Get all available batch IDs from the results directory.
        
        Returns:
            List[str]: List of batch IDs (folder names) in the results directory
        """
        batch_ids = []
        
        try:
            # Check if results directory exists
            if os.path.exists(self.results_dir):
                for item in os.listdir(self.results_dir):
                    item_path = os.path.join(self.results_dir, item)
                    
                    # Check if it's a directory and follows batch naming pattern
                    if os.path.isdir(item_path) and (
                        item.startswith("job_") or 
                        item.startswith("batch_")
                    ):
                        # Verify it's a valid batch by checking for status file
                        status_file = os.path.join(item_path, "status.json")
                        
                        if os.path.exists(status_file):
                            batch_ids.append(item)
        
        except Exception as e:
            logger.error(f"Error getting batch IDs: {e}")
        
        return batch_ids

    def set_batch_name(self, batch_id: str, batch_name: str) -> bool:
        """
        Set a custom name for a batch by adding it to the job_id.txt file.
        The batch name will be added as a second line in the file.
        
        Args:
            batch_id: The batch ID
            batch_name: The name to set for the batch
            
        Returns:
            bool: True if the name was set successfully, False otherwise
        """
        try:
            batch_dir = os.path.join(self.results_dir, batch_id)
            job_id_file = os.path.join(batch_dir, "job_id.txt")
            
            if not os.path.exists(batch_dir):
                logger.error(f"Batch directory not found: {batch_id}")
                return False
                
            # Read existing content
            content = []
            if os.path.exists(job_id_file):
                with open(job_id_file, 'r', encoding='utf-8') as f:
                    content = f.read().splitlines()
            
            # Ensure the file has at least one line (the batch ID)
            if not content:
                content.append(batch_id)
            
            # Set or update the batch name as the second line
            if len(content) > 1:
                content[1] = batch_name
            else:
                content.append(batch_name)
            
            # Write back the content
            with open(job_id_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(content))
            
            logger.info(f"Set batch name '{batch_name}' for batch {batch_id}")
            return True
        
        except Exception as e:
            logger.error(f"Error setting batch name for {batch_id}: {e}")
            return False
    
    def get_batch_name(self, batch_id: str) -> Optional[str]:
        """
        Get the custom name of a batch from the job_id.txt file.
        Returns the second line of the file if available.
        
        Args:
            batch_id: The batch ID
            
        Returns:
            Optional[str]: The batch name if available, None otherwise
        """
        try:
            job_id_file = os.path.join(self.results_dir, batch_id, "job_id.txt")
            
            if not os.path.exists(job_id_file):
                return None
            
            with open(job_id_file, 'r', encoding='utf-8') as f:
                lines = f.read().splitlines()
                
                # Return the second line if available
                if len(lines) > 1:
                    return lines[1]
            
            # If there's no second line, return None
            return None
        
        except Exception as e:
            logger.error(f"Error getting batch name for {batch_id}: {e}")
            return None

    def delete_batch(self, batch_id: str) -> bool:
        """
        Delete a batch folder by its batch ID.
        
        Args:
            batch_id: The batch ID to delete
            
        Returns:
            bool: True if the batch was successfully deleted, False otherwise
        """
        try:
            batch_dir = os.path.join(self.results_dir, batch_id)
            
            # Check if the directory exists
            if not os.path.exists(batch_dir):
                logger.error(f"Batch directory not found: {batch_id}")
                return False
            
            # Check if it's a valid batch directory pattern for safety
            if not (batch_id.startswith("batch_") or batch_id.startswith("job_")):
                logger.error(f"Invalid batch ID pattern: {batch_id}")
                return False
            
            # Remove the directory and all its contents
            import shutil
            shutil.rmtree(batch_dir)
            
            logger.info(f"Successfully deleted batch: {batch_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting batch {batch_id}: {e}")
            return False
