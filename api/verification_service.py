import os
import sys
import json
import time
import threading
import subprocess
import logging
import tempfile
import traceback
import csv
import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional, Generator, Union, Tuple, Set

# Add parent directory to path to import models
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import models
from models.controller import VerificationController
from models.common import EmailVerificationResult, VALID, INVALID, RISKY, CUSTOM

logger = logging.getLogger(__name__)
# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

class VerificationService:
    """Service for email verification operations."""
    
    def __init__(self):
        """Initialize the verification service."""
        self.controller = VerificationController()
        self.active_jobs = {}
        self.results_dir = "./results"
        
        # Ensure results directory exists
        os.makedirs(self.results_dir, exist_ok=True)
    
    def verify_single_email(self, email: str) -> Dict[str, Any]:
        """
        Verify a single email address.
        
        Args:
            email: The email address to verify
            
        Returns:
            Dict[str, Any]: The verification result
        """
        try:
            # Verify the email using the controller
            result = self.controller.verify_email(email)
            
            # Convert the result to a dictionary
            return self._result_to_dict(result)
        except Exception as e:
            logger.error(f"Error verifying email {email}: {e}")
            return {
                'email': email,
                'category': RISKY,
                'reason': f"Verification error: {str(e)}",
                'provider': self._detect_provider(email),
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'error': str(e)
            }
    
    def _detect_provider(self, email: str) -> str:
        """
        Detect the email provider based on domain.
        
        Args:
            email: The email address
            
        Returns:
            str: The provider name (google, microsoft, yahoo, or others)
        """
        domain = email.split('@')[-1].lower()
        
        if any(x in domain for x in ['gmail', 'googlemail', 'google']):
            return 'google'
        elif any(x in domain for x in ['outlook', 'hotmail', 'live', 'msn', 'microsoft']):
            return 'microsoft'
        elif any(x in domain for x in ['yahoo', 'ymail']):
            return 'yahoo'
        else:
            # Try to get MX record information if available
            try:
                import dns.resolver
                mx_records = dns.resolver.resolve(domain, 'MX')
                mx_record = str(mx_records[0].exchange).lower()
                
                if any(x in mx_record for x in ['google', 'gmail']):
                    return 'google'
                elif any(x in mx_record for x in ['outlook', 'microsoft']):
                    return 'microsoft'
                elif any(x in mx_record for x in ['yahoo']):
                    return 'yahoo'
                else:
                    return 'other'
            except:
                return 'other'

    def get_job_id(self) -> str:
        """
        Generate a unique job ID for batch verification.
        
        Returns:
            str: A unique job ID
        """
        timestamp = int(time.time())
        random_id = uuid.uuid4().hex[:8]
        return f"batch_{timestamp}_{random_id}"

    def verify_batch_emails_stream(self, emails: List[str], job_id: str) -> Generator[Dict[str, Any], None, None]:
        """
        Verify a batch of email addresses using terminalController and stream results as they become available.
        
        Args:
            emails: List of email addresses to verify
            job_id: Unique identifier for this verification job
            
        Returns:
            Generator[Dict[str, Any], None, None]: Generator yielding verification results
        """
        # Create job directory
        job_dir = os.path.join(self.results_dir, job_id)
        os.makedirs(job_dir, exist_ok=True)
        
        # Create emails.csv file for terminalController
        emails_file = os.path.join(job_dir, "emails.csv")
        with open(emails_file, 'w', encoding='utf-8', newline='') as f:
            for email in emails:
                f.write(f"{email}\n")
        
        # Initialize job status
        self.active_jobs[job_id] = {
            'job_id': job_id,
            'status': 'started',
            'total_emails': len(emails),
            'verified_emails': 0,
            'start_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'end_time': None,
            'results': {
                VALID: 0,
                INVALID: 0,
                RISKY: 0,
                CUSTOM: 0
            },
            'email_results': {}  # Store only minimal email results
        }
        
        # Save initial status
        self._save_job_status(job_id)
        
        # Yield initial status with batch ID as header
        yield {
            'header': f"Batch ID: {job_id}",
            'job_id': job_id,
            'status': 'started',
            'total_emails': len(emails),
            'message': 'Batch verification started',
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Determine terminal count based on email count
        num_terminals = self._determine_terminal_count(len(emails))
        
        # Create output queue for terminal monitoring
        output_queue = []
        
        # Create a set to track which emails have been verified
        verified_emails = set()
        
        # Start terminal controller in a separate thread
        terminal_thread = threading.Thread(
            target=self._run_terminal_controller,
            args=(emails_file, job_id, num_terminals, output_queue)
        )
        terminal_thread.daemon = True
        terminal_thread.start()
        
        # Monitor for results and yield them as they become available
        try:
            # Maximum wait time for verification (in seconds)
            max_wait_time = 600  # 10 minutes
            start_time = time.time()
            last_activity_time = time.time()
            last_verified_count = 0
            
            # Keep monitoring until all emails are verified or timeout occurs
            while len(verified_emails) < len(emails):
                # Check if we've exceeded the maximum wait time
                current_time = time.time()
                if current_time - start_time > max_wait_time:
                    logger.warning(f"Maximum wait time exceeded for job {job_id}. Verifying remaining emails.")
                    break
                
                # Check if there's been no activity for a while
                if current_time - last_activity_time > 60 and not terminal_thread.is_alive():
                    logger.warning(f"No activity for 60 seconds and terminal controller has stopped for job {job_id}.")
                    # Only break if we've verified some emails and there's been no progress
                    if len(verified_emails) > 0 and len(verified_emails) == last_verified_count:
                        break
                
                # Check data files for new results
                new_results = self._check_data_files_for_results(emails, verified_emails, job_id)
                
                # Add header to result before yielding
                for result in new_results:
                    verified_emails.add(result['email'])
                    result['header'] = f"Batch ID: {job_id}"
                    yield result
                
                # Update activity tracking
                if len(verified_emails) > last_verified_count:
                    last_activity_time = current_time
                    last_verified_count = len(verified_emails)
                
                # Sleep to avoid high CPU usage
                time.sleep(0.5)
            
            # If we still haven't verified all emails, mark remaining as risky
            remaining_emails = set(emails) - verified_emails
            if remaining_emails:
                logger.warning(f"Marking {len(remaining_emails)} unverified emails as risky for job {job_id}")
                
                for email in remaining_emails:
                    # Add header to result before yielding
                    result = {
                        'header': f"Batch ID: {job_id}",
                        'email': email,
                        'status': RISKY,
                        'provider': self._detect_provider(email),
                        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        'reason': 'Verification timed out or incomplete'
                    }
                    
                    # Update job status
                    if job_id in self.active_jobs:
                        if email not in self.active_jobs[job_id]['email_results']:
                            self.active_jobs[job_id]['verified_emails'] += 1
                            self.active_jobs[job_id]['results'][RISKY] += 1
                            
                            # Store minimal result
                            self.active_jobs[job_id]['email_results'][email] = {
                                "email": email,
                                "category": RISKY,
                                "provider": result['provider']
                            }
                    
                    # Yield the result
                    verified_emails.add(email)
                    yield result
                
                # Save updated status
                self._save_job_status(job_id)
            
            # Update job status to completed
            if job_id in self.active_jobs:
                self.active_jobs[job_id]['status'] = 'completed'
                self.active_jobs[job_id]['end_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self._save_job_status(job_id)
            
            # Yield final status
            yield {
                'header': f"Batch ID: {job_id}",
                'job_id': job_id,
                'status': 'completed',
                'total_emails': len(emails),
                'verified_emails': len(verified_emails),
                'results': self.active_jobs[job_id]['results'] if job_id in self.active_jobs else {},
                'message': 'Batch verification completed',
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
        except Exception as e:
            logger.error(f"Error in batch verification stream: {e}")
            logger.error(traceback.format_exc())
            
            # Update job status to failed
            if job_id in self.active_jobs:
                self.active_jobs[job_id]['status'] = 'failed'
                self.active_jobs[job_id]['end_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.active_jobs[job_id]['error'] = str(e)
                self._save_job_status(job_id)
            
            # Yield error status
            yield {
                'header': f"Batch ID: {job_id}",
                'job_id': job_id,
                'status': 'failed',
                'error': str(e),
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
    
    def _check_data_files_for_results(self, emails: List[str], verified_emails: Set[str], job_id: str) -> List[Dict[str, Any]]:
        """
        Check data files for new verification results.
        
        Args:
            emails: List of emails to verify
            verified_emails: Set of emails that have already been verified
            job_id: Unique identifier for this verification job
            
        Returns:
            List[Dict[str, Any]]: List of new verification results
        """
        new_results = []
        
        # Create a set of emails to check (only those not yet verified)
        emails_to_check = set(emails) - verified_emails
        
        # Check each category's data file
        for category, category_code in [("Valid", VALID), ("Invalid", INVALID), ("Risky", RISKY), ("Custom", CUSTOM)]:
            data_file = os.path.join("./data", f"{category}.csv")
            if os.path.exists(data_file):
                try:
                    with open(data_file, 'r', encoding='utf-8', newline='') as f:
                        reader = csv.reader(f)
                        for row in reader:
                            if row and row[0] in emails_to_check:
                                # Create a result for this email
                                email = row[0]
                                provider = self._detect_provider(email)
                                
                                # Try to get reason from results file
                                reason = self._get_reason_from_results(email, category_code)
                                
                                result = {
                                    'email': email,
                                    'status': category_code,
                                    'provider': provider,
                                    'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    'reason': reason
                                }
                                
                                # Update job status
                                if job_id in self.active_jobs:
                                    if email not in self.active_jobs[job_id]['email_results']:
                                        self.active_jobs[job_id]['verified_emails'] += 1
                                        self.active_jobs[job_id]['results'][category_code] += 1
                                        
                                        # Store minimal result
                                        self.active_jobs[job_id]['email_results'][email] = {
                                            "email": email,
                                            "category": category_code,
                                            "provider": provider
                                        }
                                        
                                        # Save updated status
                                        self._save_job_status(job_id)
                                
                                # Add to new results
                                new_results.append(result)
                                
                                # Remove from emails to check
                                emails_to_check.remove(email)
                except Exception as e:
                    logger.error(f"Error reading {category} data file: {e}")
        
        return new_results
    
    def _get_reason_from_results(self, email: str, category: str) -> str:
        """
        Get verification reason from results file.
        
        Args:
            email: The email address
            category: The verification category
            
        Returns:
            str: The verification reason
        """
        # Map category to results file
        category_map = {
            VALID: "valid.csv",
            INVALID: "invalid.csv",
            RISKY: "risky.csv",
            CUSTOM: "custom.csv"
        }
        
        if category not in category_map:
            return "Unknown"
        
        results_file = os.path.join(self.results_dir, category_map[category])
        
        if not os.path.exists(results_file):
            return "Unknown"
        
        try:
            with open(results_file, 'r', encoding='utf-8', newline='') as f:
                reader = csv.reader(f)
                next(reader)  # Skip header
                for row in reader:
                    if row and row[0] == email:
                        # Return reason (column 3)
                        return row[3] if len(row) > 3 and row[3] else "Unknown"
        except Exception as e:
            logger.error(f"Error reading reason from results file: {e}")
        
        return "Unknown"
    
    def _run_terminal_controller(self, emails_file: str, job_id: str, num_terminals: int, output_queue: List) -> None:
        """
        Run terminalController.py to verify emails in multiple terminals.
        
        Args:
            emails_file: Path to the CSV file containing emails
            job_id: Unique identifier for this verification job
            num_terminals: Number of terminals to use
            output_queue: Queue to store terminal controller output
        """
        try:
            # Update job status
            if job_id in self.active_jobs:
                self.active_jobs[job_id]['status'] = 'processing'
                self._save_job_status(job_id)
            
            # Get the absolute path to terminalController.py
            terminal_controller_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "terminalController.py"
            )
            
            # Create a temporary file to pass the job ID to terminalController
            job_id_file = os.path.join(os.path.dirname(emails_file), "job_id.txt")
            with open(job_id_file, 'w', encoding='utf-8') as f:
                f.write(job_id)
            
            # Log the command that will be executed
            cmd = [
                sys.executable,
                terminal_controller_path,
                "--csv-path", emails_file,
                "--num-terminals", str(num_terminals),
                "--background",
                "--job-id", job_id
            ]
            
            logger.info(f"Running terminal controller: {' '.join(cmd)}")
            
            # Execute terminalController.py as a separate process
            # IMPORTANT: shell=False prevents blocking issues
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=False  # This is crucial for non-blocking execution
            )
            
            # Start threads to capture stdout and stderr
            def capture_output(stream, prefix):
                for line in iter(stream.readline, ''):
                    if line.strip():
                        logger.info(f"{prefix}: {line.strip()}")
                        output_queue.append(line.strip())
            
            stdout_thread = threading.Thread(target=capture_output, args=(process.stdout, "STDOUT"))
            stderr_thread = threading.Thread(target=capture_output, args=(process.stderr, "STDERR"))
            
            stdout_thread.daemon = True
            stderr_thread.daemon = True
            
            stdout_thread.start()
            stderr_thread.start()
            
            # Wait for process to complete with timeout
            try:
                process.wait(timeout=300)  # 5 minute timeout
            except subprocess.TimeoutExpired:
                logger.warning(f"Terminal controller process timed out for job {job_id}")
                # Don't kill the process, let it continue running
            
            stdout_thread.join(timeout=5)
            stderr_thread.join(timeout=5)
            
            # Check return code if process has completed
            if process.poll() is not None:
                if process.returncode != 0:
                    logger.error(f"Terminal controller process failed with return code {process.returncode}")
                    if job_id in self.active_jobs:
                        self.active_jobs[job_id]['status'] = 'failed'
                        self.active_jobs[job_id]['error'] = f"Terminal controller process failed with return code {process.returncode}"
                        self._save_job_status(job_id)
                else:
                    logger.info("Terminal controller process completed successfully")
                    # Don't mark as completed yet, wait for all emails to be verified
            
        except Exception as e:
            logger.error(f"Error running terminal controller: {e}")
            logger.error(traceback.format_exc())
            
            if job_id in self.active_jobs:
                self.active_jobs[job_id]['status'] = 'failed'
                self.active_jobs[job_id]['error'] = str(e)
                self._save_job_status(job_id)
    
    def _determine_terminal_count(self, email_count: int) -> int:
        """
        Determine the number of terminals to use based on email count.
        
        Args:
            email_count: Number of emails to verify
            
        Returns:
            int: Number of terminals to use
        """
        if email_count <= 3:
            return 1
        elif email_count <= 10:
            return 3
        elif email_count <= 15:
            return 5
        elif email_count <= 20:
            return 9
        elif email_count <= 24:
            return 11
        elif email_count <= 30:
            return 13
        elif email_count <= 50:
            return 15
        elif email_count <= 200:
            return 20
        elif email_count <= 500:
            return 25
        else:
            return 30  # Maximum number of terminals
    
    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the status of a verification job.
        
        Args:
            job_id: Unique identifier for the verification job
            
        Returns:
            Optional[Dict[str, Any]]: The job status, or None if not found
        """
        # Check if job is in active jobs
        if job_id in self.active_jobs:
            return self.active_jobs[job_id]
        
        # Check if job status file exists
        status_file = os.path.join(self.results_dir, job_id, "status.json")
        if os.path.exists(status_file):
            try:
                with open(status_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading job status for {job_id}: {e}")
        
        return None
    
    def _save_job_status(self, job_id: str) -> None:
        """
        Save job status to a file.
        
        Args:
            job_id: Unique identifier for the verification job
        """
        if job_id not in self.active_jobs:
            return
        
        job_dir = os.path.join(self.results_dir, job_id)
        os.makedirs(job_dir, exist_ok=True)
        
        status_file = os.path.join(job_dir, "status.json")
        
        try:
            with open(status_file, 'w', encoding='utf-8') as f:
                # Create a copy of the job status with simplified email results
                job_status = self.active_jobs[job_id].copy()
                
                # Keep only minimal information for email results
                simplified_results = {}
                for email, result in job_status['email_results'].items():
                    simplified_results[email] = {
                        "email": email,
                        "category": result["category"],
                        "provider": result["provider"]
                    }
                
                job_status['email_results'] = simplified_results
                
                json.dump(job_status, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving job status for {job_id}: {e}")
    
    def _result_to_dict(self, result: EmailVerificationResult) -> Dict[str, Any]:
        """
        Convert an EmailVerificationResult to a dictionary.
        
        Args:
            result: The verification result
            
        Returns:
            Dict[str, Any]: The result as a dictionary
        """
        # Detect provider if not already set
        provider = result.provider if result.provider else self._detect_provider(result.email)
        
        return {
            'email': result.email,
            'category': result.category,
            'reason': result.reason,
            'provider': provider,
            'timestamp': result.timestamp,
            'details': result.details
        }
