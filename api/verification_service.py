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
from datetime import datetime
from typing import Dict, List, Any, Optional, Generator, Union, Tuple

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
        
        # Yield initial status
        yield {
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
        
        # Start terminal controller in a separate thread
        terminal_thread = threading.Thread(
            target=self._run_terminal_controller,
            args=(emails_file, job_id, num_terminals, output_queue)
        )
        terminal_thread.daemon = True
        terminal_thread.start()
        
        # Start monitor thread to yield results
        for result in self._monitor_terminal_controller_stream(job_id, output_queue, emails):
            yield result
            
        # Wait for terminal thread to complete
        terminal_thread.join(timeout=60)
        
        # Yield final status
        yield {
            'job_id': job_id,
            'status': self.active_jobs[job_id]['status'],
            'total_emails': len(emails),
            'verified_emails': self.active_jobs[job_id]['verified_emails'],
            'results': self.active_jobs[job_id]['results'],
            'message': f"Batch verification {self.active_jobs[job_id]['status']}",
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    
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
            import importlib.util
            import sys
            
            # Update job status
            if job_id in self.active_jobs:
                self.active_jobs[job_id]['status'] = 'processing'
                self._save_job_status(job_id)
            
            # Get the absolute path to terminalController.py
            terminal_controller_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "terminalController.py"
            )
            
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
            
            # Wait for process to complete
            process.wait()
            
            stdout_thread.join(timeout=5)
            stderr_thread.join(timeout=5)
            
            # Check return code
            if process.returncode != 0:
                logger.error(f"Terminal controller process failed with return code {process.returncode}")
                if job_id in self.active_jobs:
                    self.active_jobs[job_id]['status'] = 'failed'
                    self.active_jobs[job_id]['error'] = f"Terminal controller process failed with return code {process.returncode}"
                    self._save_job_status(job_id)
            else:
                logger.info("Terminal controller process completed successfully")
                if job_id in self.active_jobs:
                    self.active_jobs[job_id]['status'] = 'completed'
                    self._save_job_status(job_id)
                    
            # Process results
            self._process_terminal_results(job_id)
            
        except Exception as e:
            logger.error(f"Error running terminal controller: {e}")
            logger.error(traceback.format_exc())
            
            if job_id in self.active_jobs:
                self.active_jobs[job_id]['status'] = 'failed'
                self.active_jobs[job_id]['error'] = str(e)
                self._save_job_status(job_id)
    
    def _monitor_terminal_controller_stream(self, job_id: str, output_queue: List, emails: List[str]) -> Generator[Dict[str, Any], None, None]:
        """
        Monitor the terminal controller output and yield results as they become available.
        
        Args:
            job_id: Unique identifier for this verification job
            output_queue: Queue containing terminal controller output
            emails: List of email addresses to verify
            
        Returns:
            Generator[Dict[str, Any], None, None]: Generator yielding verification results
        """
        # Track processed lines to avoid duplicates
        processed_lines = set()
        
        # Track progress for each email
        email_progress = {email: False for email in emails}
        
        # Create a mapping of filename patterns to categories
        category_patterns = {
            "Valid": VALID,
            "Invalid": INVALID,
            "Risky": RISKY,
            "Custom": CUSTOM
        }
        
        # Initialize email result counters
        counts = {
            VALID: 0,
            INVALID: 0,
            RISKY: 0,
            CUSTOM: 0
        }
        
        # Run until all emails are verified or until terminalController completes
        max_wait_time = 300  # Maximum wait time in seconds
        start_time = time.time()
        last_activity_time = time.time()
        last_processed_count = 0
        
        while (not all(email_progress.values()) and 
               (time.time() - start_time < max_wait_time) and
               (time.time() - last_activity_time < 60)):  # Timeout after 60 seconds of inactivity
            
            # Process any new output from terminal controller
            current_queue = list(output_queue)  # Make a copy to avoid concurrent modification
            
            # Check for activity
            processed_count = 0
            
            for line in current_queue:
                line_key = line.strip()
                if line_key and line_key not in processed_lines:
                    processed_lines.add(line_key)
                    processed_count += 1
                    
                    # Look for email verification results in the output
                    if any(category in line for category in category_patterns.keys()):
                        self._extract_and_process_results(line, category_patterns, email_progress, job_id, counts)
            
            # If we processed any lines, update the last activity time
            if processed_count > last_processed_count:
                last_activity_time = time.time()
                last_processed_count = processed_count
            
            # Check data files for results
            for category, category_code in category_patterns.items():
                data_file = os.path.join("./data", f"{category}.csv")
                if os.path.exists(data_file):
                    try:
                        with open(data_file, 'r', encoding='utf-8', newline='') as f:
                            reader = csv.reader(f)
                            for row in reader:
                                if row and row[0] in email_progress and not email_progress[row[0]]:
                                    # Mark email as processed
                                    email_progress[row[0]] = True
                                    
                                    # Update job status
                                    if job_id in self.active_jobs:
                                        if row[0] not in self.active_jobs[job_id]['email_results']:
                                            self.active_jobs[job_id]['verified_emails'] += 1
                                            counts[category_code] += 1
                                            
                                            # Store minimal result
                                            provider = self._detect_provider(row[0])
                                            self.active_jobs[job_id]['email_results'][row[0]] = {
                                                "email": row[0],
                                                "category": category_code,
                                                "provider": provider
                                            }
                                            
                                            # Update results counter
                                            self.active_jobs[job_id]['results'] = counts.copy()
                                            
                                            # Save updated status
                                            self._save_job_status(job_id)
                                            
                                            # Yield the result
                                            yield {
                                                'email': row[0],
                                                'status': category_code,
                                                'provider': provider,
                                                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                            }
                    except Exception as e:
                        logger.error(f"Error reading {category} data file: {e}")
            
            # Sleep to avoid high CPU usage
            time.sleep(0.5)
            
            # Check job status
            if job_id in self.active_jobs:
                job_status = self.active_jobs[job_id]['status']
                if job_status == 'completed' or job_status == 'failed':
                    break
        
        # Final check for any missed emails
        for email, processed in email_progress.items():
            if not processed:
                # Check if it's in the job results
                if job_id in self.active_jobs and email in self.active_jobs[job_id]['email_results']:
                    continue
                    
                # Check data files one last time
                for category, category_code in category_patterns.items():
                    data_file = os.path.join("./data", f"{category}.csv")
                    if os.path.exists(data_file):
                        try:
                            with open(data_file, 'r', encoding='utf-8', newline='') as f:
                                reader = csv.reader(f)
                                if any(row and row[0] == email for row in reader):
                                    # Mark email as processed
                                    email_progress[email] = True
                                    
                                    # Update job status
                                    if job_id in self.active_jobs:
                                        if email not in self.active_jobs[job_id]['email_results']:
                                            self.active_jobs[job_id]['verified_emails'] += 1
                                            counts[category_code] += 1
                                            
                                            # Store minimal result
                                            provider = self._detect_provider(email)
                                            self.active_jobs[job_id]['email_results'][email] = {
                                                "email": email,
                                                "category": category_code,
                                                "provider": provider
                                            }
                                            
                                            # Update results counter
                                            self.active_jobs[job_id]['results'] = counts.copy()
                                            
                                            # Save updated status
                                            self._save_job_status(job_id)
                                            
                                            # Yield the result
                                            yield {
                                                'email': email,
                                                'status': category_code,
                                                'provider': provider,
                                                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                            }
                                    break
                        except Exception as e:
                            logger.error(f"Error reading {category} data file in final check: {e}")
    
    def _extract_and_process_results(self, line: str, category_patterns: Dict[str, str], 
                                   email_progress: Dict[str, bool], job_id: str, 
                                   counts: Dict[str, int]) -> None:
        """
        Extract and process email verification results from terminal output.
        
        Args:
            line: Output line from terminal controller
            category_patterns: Mapping of filename patterns to categories
            email_progress: Tracking of which emails have been processed
            job_id: Unique identifier for this verification job
            counts: Counter for different result categories
        """
        try:
            # Extract email address from the line
            # Look for common patterns in the output
            email = None
            category = None
            
            # Try to extract email and category
            for pattern, category_code in category_patterns.items():
                if pattern in line:
                    category = category_code
                    # Try to extract the email from the line
                    import re
                    email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', line)
                    if email_match:
                        email = email_match.group(0)
                        break
            
            # If we found both email and category
            if email and category and email in email_progress and not email_progress[email]:
                # Mark email as processed
                email_progress[email] = True
                
                # Update job status
                if job_id in self.active_jobs:
                    if email not in self.active_jobs[job_id]['email_results']:
                        self.active_jobs[job_id]['verified_emails'] += 1
                        counts[category] += 1
                        
                        # Store minimal result
                        provider = self._detect_provider(email)
                        self.active_jobs[job_id]['email_results'][email] = {
                            "email": email,
                            "category": category,
                            "provider": provider
                        }
                        
                        # Update results counter
                        self.active_jobs[job_id]['results'] = counts.copy()
                        
                        # Save updated status
                        self._save_job_status(job_id)
                        
                        # No need to yield here, as this will be caught by the file monitoring
        
        except Exception as e:
            logger.error(f"Error extracting results from line: {e}")
    
    def _process_terminal_results(self, job_id: str) -> None:
        """
        Process results from terminal controller after it completes.
        
        Args:
            job_id: Unique identifier for this verification job
        """
        try:
            # Get job directory
            job_dir = os.path.join(self.results_dir, job_id)
            
            # Update job status
            if job_id in self.active_jobs:
                # Count results from the data files
                valid_count = self._count_emails_in_file(os.path.join("./data", "Valid.csv"))
                invalid_count = self._count_emails_in_file(os.path.join("./data", "Invalid.csv"))
                risky_count = self._count_emails_in_file(os.path.join("./data", "Risky.csv"))
                custom_count = self._count_emails_in_file(os.path.join("./data", "Custom.csv"))
                
                # Update results counts
                self.active_jobs[job_id]['results'] = {
                    VALID: valid_count,
                    INVALID: invalid_count,
                    RISKY: risky_count,
                    CUSTOM: custom_count
                }
                
                # Update verified emails count
                self.active_jobs[job_id]['verified_emails'] = valid_count + invalid_count + risky_count + custom_count
                
                # Save updated status
                self._save_job_status(job_id)
        
        except Exception as e:
            logger.error(f"Error processing terminal results: {e}")
            logger.error(traceback.format_exc())
    
    def _count_emails_in_file(self, file_path: str) -> int:
        """
        Count the number of emails in a CSV file.
        
        Args:
            file_path: Path to the CSV file
            
        Returns:
            int: Number of emails in the file
        """
        if not os.path.exists(file_path):
            return 0
        
        try:
            with open(file_path, 'r', encoding='utf-8', newline='') as f:
                reader = csv.reader(f)
                return sum(1 for row in reader if row and '@' in row[0])
        except Exception as e:
            logger.error(f"Error counting emails in {file_path}: {e}")
            return 0
    
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
            return 20
        elif email_count <= 24:
            return 11
        elif email_count <= 30:
            return 13
        elif email_count <= 50:
            return 15
        elif email_count <= 200:
            return 17
        elif email_count <= 500:
            return 19
        else:
            return 20  # Maximum number of terminals
    
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

