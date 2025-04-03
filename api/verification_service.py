import os
import sys
import json
import time
import threading
import subprocess
import logging
import tempfile
from datetime import datetime
from typing import Dict, List, Any, Optional, Generator

# Add parent directory to path to import models
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import models
from models.controller import VerificationController
from models.common import EmailVerificationResult, VALID, INVALID, RISKY, CUSTOM

logger = logging.getLogger(__name__)

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
    
    def verify_batch_emails(self, emails: List[str], job_id: str) -> None:
        """
        Verify a batch of email addresses using terminalController.
        
        Args:
            emails: List of email addresses to verify
            job_id: Unique identifier for this verification job
        """
        # Create job directory
        job_dir = os.path.join(self.results_dir, job_id)
        os.makedirs(job_dir, exist_ok=True)
        
        # Save emails to a temporary file
        emails_file = os.path.join(job_dir, "emails.csv")
        with open(emails_file, 'w', encoding='utf-8') as f:
            for email in emails:
                f.write(f"{email}\n")
        
        # Update job status
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
            'verification_progress': {},  # Track detailed verification progress
            'email_results': {}  # Store results for each email
        }
        
        # Save initial status
        self._save_job_status(job_id)
        
        # Start verification in a separate thread
        thread = threading.Thread(target=self._run_terminal_controller, args=(emails_file, job_id))
        thread.daemon = True
        thread.start()
    
    def verify_batch_emails_stream(self, emails: List[str], job_id: str) -> Generator[Dict[str, Any], None, None]:
        """
        Verify a batch of email addresses and stream results as they become available.
        
        Args:
            emails: List of email addresses to verify
            job_id: Unique identifier for this verification job
            
        Returns:
            Generator[Dict[str, Any], None, None]: Generator yielding verification results
        """
        # Create job directory
        job_dir = os.path.join(self.results_dir, job_id)
        os.makedirs(job_dir, exist_ok=True)
        
        # Save emails to a temporary file
        emails_file = os.path.join(job_dir, "emails.csv")
        with open(emails_file, 'w', encoding='utf-8') as f:
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
            'verification_progress': {},  # Track detailed verification progress
            'email_results': {}  # Store results for each email
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
        
        # Determine number of terminals based on email count
        num_terminals = self._determine_terminal_count(emails_file)
        
        # Update job status
        self.active_jobs[job_id]['status'] = 'running'
        self.active_jobs[job_id]['num_terminals'] = num_terminals
        self._save_job_status(job_id)
        
        # Create command to run terminalController with verbose output
        cmd = [
            sys.executable,
            "terminalController.py",
            "--csv-path", emails_file,
            "--job-id", job_id,
            "--num-terminals", str(num_terminals),
            "--background",
            "--verbose"  # Add verbose flag for detailed output
        ]
        
        logger.info(f"Starting terminalController for job {job_id} with {num_terminals} terminals")
        logger.info(f"Command: {' '.join(cmd)}")
        
        # Run terminalController as a subprocess
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # Line buffered
            universal_newlines=True
        )
        
        # Create a queue for results
        result_queue = []
        
        # Create a thread to monitor the process output
        monitor_thread = threading.Thread(
            target=self._monitor_terminal_controller_stream,
            args=(process, job_id, result_queue)
        )
        monitor_thread.daemon = True
        monitor_thread.start()
        
        # Keep track of emails that have been yielded
        yielded_emails = set()
        
        # Stream results as they become available
        while True:
            # Check if process has completed
            if process.poll() is not None:
                # Process has completed
                break
            
            # Check for new results
            if result_queue:
                result = result_queue.pop(0)
                email = result.get('email')
                
                if email and email not in yielded_emails:
                    yielded_emails.add(email)
                    yield result
            
            # Sleep briefly to avoid high CPU usage
            time.sleep(0.1)
        
        # Check if process completed successfully
        if process.returncode == 0:
            # Update job status
            self.active_jobs[job_id]['status'] = 'completed'
            self.active_jobs[job_id]['end_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Parse results
            self._parse_batch_results(job_id)
            
            # Update the original emails.csv file with results
            self._update_emails_csv_with_results(job_id)
            
            # Yield final status
            yield {
                'job_id': job_id,
                'status': 'completed',
                'total_emails': len(emails),
                'verified_emails': len(yielded_emails),
                'message': 'Batch verification completed',
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        else:
            # Update job status
            self.active_jobs[job_id]['status'] = 'failed'
            self.active_jobs[job_id]['end_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.active_jobs[job_id]['error'] = "terminalController process failed"
            
            # Yield error status
            yield {
                'job_id': job_id,
                'status': 'failed',
                'error': "terminalController process failed",
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        
        # Save final status
        self._save_job_status(job_id)
    
    def _run_terminal_controller(self, emails_file: str, job_id: str) -> None:
        """
        Run terminalController directly to verify emails.
        
        Args:
            emails_file: Path to the file containing emails
            job_id: Unique identifier for this verification job
        """
        try:
            # Determine number of terminals based on email count
            num_terminals = self._determine_terminal_count(emails_file)
            
            # Update job status
            self.active_jobs[job_id]['status'] = 'running'
            self.active_jobs[job_id]['num_terminals'] = num_terminals
            self._save_job_status(job_id)
            
            # Create command to run terminalController with verbose output
            cmd = [
                sys.executable,
                "terminalController.py",
                "--csv-path", emails_file,
                "--job-id", job_id,
                "--num-terminals", str(num_terminals),
                "--background",
                "--verbose"  # Add verbose flag for detailed output
            ]
            
            logger.info(f"Starting terminalController for job {job_id} with {num_terminals} terminals")
            logger.info(f"Command: {' '.join(cmd)}")
            
            # Run terminalController as a subprocess with shell=False to avoid blocking
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # Line buffered
                universal_newlines=True,
                shell=False  # Important: Don't use shell to avoid blocking
            )
            
            # Monitor the process output
            self._monitor_terminal_controller(process, job_id)
            
            # Wait for process to complete
            returncode = process.wait()
            
            # Check if process completed successfully
            if returncode == 0:
                # Update job status
                self.active_jobs[job_id]['status'] = 'completed'
                self.active_jobs[job_id]['end_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # Parse results
                self._parse_batch_results(job_id)
                
                # Update the original emails.csv file with results
                self._update_emails_csv_with_results(job_id)
            else:
                # Update job status
                self.active_jobs[job_id]['status'] = 'failed'
                self.active_jobs[job_id]['end_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.active_jobs[job_id]['error'] = "terminalController process failed"
            
            # Save final status
            self._save_job_status(job_id)
            
        except Exception as e:
            logger.error(f"Error running batch verification for job {job_id}: {e}")
            
            # Update job status
            if job_id in self.active_jobs:
                self.active_jobs[job_id]['status'] = 'failed'
                self.active_jobs[job_id]['end_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.active_jobs[job_id]['error'] = str(e)
                
                # Save final status
                self._save_job_status(job_id)
    
    def _update_emails_csv_with_results(self, job_id: str) -> None:
        """
        Update the original emails.csv file with verification results.
        
        Args:
            job_id: Unique identifier for the verification job
        """
        job_dir = os.path.join(self.results_dir, job_id)
        emails_file = os.path.join(job_dir, "emails.csv")
        results_file = os.path.join(job_dir, "emails_results.csv")
        
        # Get all results for this job
        valid_emails = self._read_emails_from_file(os.path.join(job_dir, f"{VALID}_Results.csv"))
        invalid_emails = self._read_emails_from_file(os.path.join(job_dir, f"{INVALID}_Results.csv"))
        risky_emails = self._read_emails_from_file(os.path.join(job_dir, f"{RISKY}_Results.csv"))
        custom_emails = self._read_emails_from_file(os.path.join(job_dir, f"{CUSTOM}_Results.csv"))
        
        # Create a mapping of email to status
        email_status = {}
        for email in valid_emails:
            email_status[email] = VALID
        for email in invalid_emails:
            email_status[email] = INVALID
        for email in risky_emails:
            email_status[email] = RISKY
        for email in custom_emails:
            email_status[email] = CUSTOM
        
        # Read original emails
        original_emails = []
        try:
            with open(emails_file, 'r', encoding='utf-8') as f:
                for line in f:
                    email = line.strip()
                    if '@' in email:
                        original_emails.append(email)
        except Exception as e:
            logger.error(f"Error reading emails file: {e}")
            return
        
        # Write results to new file
        try:
            with open(results_file, 'w', encoding='utf-8', newline='') as f:
                import csv
                writer = csv.writer(f)
                writer.writerow(["Email", "Status", "Provider"])
                
                for email in original_emails:
                    status = email_status.get(email, "unknown")
                    provider = self._detect_provider(email)
                    writer.writerow([email, status, provider])
                    
            logger.info(f"Updated emails results file for job {job_id}")
        except Exception as e:
            logger.error(f"Error writing emails results file: {e}")
    
    def _read_emails_from_file(self, file_path: str) -> List[str]:
        """
        Read emails from a CSV file.
        
        Args:
            file_path: Path to the CSV file
            
        Returns:
            List[str]: List of emails
        """
        emails = []
        
        if not os.path.exists(file_path):
            return emails
            
        try:
            import csv
            with open(file_path, 'r', encoding='utf-8', newline='') as f:
                reader = csv.reader(f)
                next(reader, None)  # Skip header
                for row in reader:
                    if row and '@' in row[0]:
                        emails.append(row[0])
        except Exception as e:
            logger.error(f"Error reading emails from {file_path}: {e}")
            
        return emails
    
    def _monitor_terminal_controller(self, process: subprocess.Popen, job_id: str) -> None:
        """
        Monitor the terminalController process and update job status.
        
        Args:
            process: The subprocess.Popen object
            job_id: Unique identifier for the verification job
        """
        # Read stdout line by line
        for line in iter(process.stdout.readline, ''):
            line = line.strip()
            if not line:
                continue
                
            logger.info(f"terminalController output: {line}")
            
            # Display verification progress in terminal
            print(line)
            
            # Update job status with progress information
            if "Terminal" in line and "RESULT:" in line:
                # Extract result information
                parts = line.split("RESULT:")
                if len(parts) > 1:
                    result_parts = parts[1].split(":")
                    if len(result_parts) > 1:
                        email = result_parts[0]
                        category = result_parts[1].lower()
                        
                        # Update verified count
                        if job_id in self.active_jobs:
                            self.active_jobs[job_id]['verified_emails'] += 1
                            
                            # Update category count
                            if category in [VALID, INVALID, RISKY, CUSTOM]:
                                self.active_jobs[job_id]['results'][category] += 1
                            
                            # Save updated status
                            self._save_job_status(job_id)
            
            # Track detailed verification progress
            elif "Verifying" in line and ":" in line:
                # Extract email being verified
                parts = line.split("Verifying")
                if len(parts) > 1:
                    email_part = parts[1].strip()
                    if '@' in email_part:
                        email = email_part.split()[0].strip().strip('"').strip("'")
                        
                        # Add verification event
                        if job_id in self.active_jobs:
                            if email not in self.active_jobs[job_id]['verification_progress']:
                                self.active_jobs[job_id]['verification_progress'][email] = []
                            
                            self.active_jobs[job_id]['verification_progress'][email].append({
                                "event": "Verification started",
                                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            })
                            
                            # Save updated status
                            self._save_job_status(job_id)
            
            # Track provider identification
            elif "Provider identified" in line and ":" in line:
                # Extract email and provider
                for email in self.active_jobs[job_id]['verification_progress']:
                    if email in line:
                        provider = line.split("Provider identified:")[1].strip()
                        
                        self.active_jobs[job_id]['verification_progress'][email].append({
                            "event": f"Provider identified: {provider}",
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        })
                        
                        # Save updated status
                        self._save_job_status(job_id)
            
            # Track verification steps
            elif any(step in line for step in ["verification", "checking", "testing", "connecting", "login"]):
                # Extract email if present
                for email in self.active_jobs[job_id]['verification_progress']:
                    if email in line:
                        self.active_jobs[job_id]['verification_progress'][email].append({
                            "event": line,
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        })
                        
                        # Save updated status
                        self._save_job_status(job_id)
            
            # Check for completion messages
            elif "All terminals have completed processing" in line:
                logger.info(f"All terminals completed for job {job_id}")
    
    def _monitor_terminal_controller_stream(self, process: subprocess.Popen, job_id: str, result_queue: List) -> None:
        """
        Monitor the terminalController process and update job status for streaming.
        
        Args:
            process: The subprocess.Popen object
            job_id: Unique identifier for the verification job
            result_queue: Queue to store results for streaming
        """
        # Read stdout line by line
        for line in iter(process.stdout.readline, ''):
            line = line.strip()
            if not line:
                continue
                
            logger.info(f"terminalController output: {line}")
            
            # Display verification progress in terminal
            print(line)
            
            # Update job status with progress information
            if "Terminal" in line and "RESULT:" in line:
                # Extract result information
                parts = line.split("RESULT:")
                if len(parts) > 1:
                    result_parts = parts[1].split(":")
                    if len(result_parts) > 1:
                        email = result_parts[0]
                        category = result_parts[1].lower()
                        
                        # Update verified count
                        if job_id in self.active_jobs:
                            self.active_jobs[job_id]['verified_emails'] += 1
                            
                            # Update category count
                            if category in [VALID, INVALID, RISKY, CUSTOM]:
                                self.active_jobs[job_id]['results'][category] += 1
                            
                            # Add result to queue for streaming
                            provider = self._detect_provider(email)
                            result = {
                                'email': email,
                                'status': category,
                                'provider': provider,
                                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            }
                            result_queue.append(result)
                            
                            # Store result in job status
                            self.active_jobs[job_id]['email_results'][email] = result
                            
                            # Save updated status
                            self._save_job_status(job_id)
            
            # Track detailed verification progress
            elif "Verifying" in line and ":" in line:
                # Extract email being verified
                parts = line.split("Verifying")
                if len(parts) > 1:
                    email_part = parts[1].strip()
                    if '@' in email_part:
                        email = email_part.split()[0].strip().strip('"').strip("'")
                        
                        # Add verification event
                        if job_id in self.active_jobs:
                            if email not in self.active_jobs[job_id]['verification_progress']:
                                self.active_jobs[job_id]['verification_progress'][email] = []
                            
                            self.active_jobs[job_id]['verification_progress'][email].append({
                                "event": "Verification started",
                                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            })
                            
                            # Save updated status
                            self._save_job_status(job_id)
            
            # Track provider identification
            elif "Provider identified" in line and ":" in line:
                # Extract email and provider
                for email in self.active_jobs[job_id]['verification_progress']:
                    if email in line:
                        provider = line.split("Provider identified:")[1].strip()
                        
                        self.active_jobs[job_id]['verification_progress'][email].append({
                            "event": f"Provider identified: {provider}",
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        })
                        
                        # Save updated status
                        self._save_job_status(job_id)
            
            # Track verification steps
            elif any(step in line for step in ["verification", "checking", "testing", "connecting", "login"]):
                # Extract email if present
                for email in self.active_jobs[job_id]['verification_progress']:
                    if email in line:
                        self.active_jobs[job_id]['verification_progress'][email].append({
                            "event": line,
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        })
                        
                        # Save updated status
                        self._save_job_status(job_id)
            
            # Check for completion messages
            elif "All terminals have completed processing" in line:
                logger.info(f"All terminals completed for job {job_id}")
    
    def _determine_terminal_count(self, emails_file: str) -> int:
        """
        Determine the number of terminals to use based on email count.
        
        Args:
            emails_file: Path to the file containing emails
            
        Returns:
            int: Number of terminals to use
        """
        try:
            # Count emails in file
            with open(emails_file, 'r', encoding='utf-8') as f:
                email_count = sum(1 for line in f if '@' in line)
            
            # Determine terminal count based on email count
            if email_count <= 10:
                return 1
            elif email_count <= 50:
                return 2
            elif email_count <= 200:
                return 4
            elif email_count <= 500:
                return 8
            else:
                return 16  # Maximum number of terminals
        except Exception as e:
            logger.error(f"Error determining terminal count: {e}")
            return 2  # Default to 2 terminals
    
    def _parse_batch_results(self, job_id: str) -> None:
        """
        Parse batch verification results.
        
        Args:
            job_id: Unique identifier for the verification job
        """
        job_dir = os.path.join(self.results_dir, job_id)
        
        # Check for results files
        valid_file = os.path.join(job_dir, f"{VALID}_Results.csv")
        invalid_file = os.path.join(job_dir, f"{INVALID}_Results.csv")
        risky_file = os.path.join(job_dir, f"{RISKY}_Results.csv")
        custom_file = os.path.join(job_dir, f"{CUSTOM}_Results.csv")
        
        # Count results
        valid_count = self._count_lines(valid_file) - 1  # Subtract header
        invalid_count = self._count_lines(invalid_file) - 1
        risky_count = self._count_lines(risky_file) - 1
        custom_count = self._count_lines(custom_file) - 1
        
        # Update job status
        if job_id in self.active_jobs:
            self.active_jobs[job_id]['verified_emails'] = valid_count + invalid_count + risky_count + custom_count
            self.active_jobs[job_id]['results'] = {
                VALID: valid_count,
                INVALID: invalid_count,
                RISKY: risky_count,
                CUSTOM: custom_count
            }
            
            # Save updated status
            self._save_job_status(job_id)
    
    def _count_lines(self, file_path: str) -> int:
        """
        Count the number of lines in a file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            int: Number of lines in the file
        """
        if not os.path.exists(file_path):
            return 0
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return sum(1 for _ in f)
        except Exception as e:
            logger.error(f"Error counting lines in {file_path}: {e}")
            return 0
    
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
                json.dump(self.active_jobs[job_id], f, indent=4)
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

