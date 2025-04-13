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
            if os.path.exists(bounce_results_dir):
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
