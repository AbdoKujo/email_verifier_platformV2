import os
import csv
import time
import uuid
import random
import logging
import imaplib
import email
import smtplib
import re
import socket
import threading
import queue
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Set
import json

from models.settings_model import SettingsModel
from models.common import EmailVerificationResult, VALID, INVALID, RISKY, CUSTOM

logger = logging.getLogger(__name__)

PENDING = "pending"

class BounceModel:
    """Model for verifying emails using the bounce method."""
    
    def __init__(self, settings_model: SettingsModel):
        """
        Initialize the bounce model.
        
        Args:
            settings_model: The settings model
        """
        self.settings_model = settings_model
        self.smtp_accounts = self.settings_model.get_smtp_accounts()
        
        # Ensure we have at least one account
        if not self.smtp_accounts:
            logger.warning("No SMTP accounts configured for bounce verification")
        
        # Create required directories
        self.results_dir = os.path.join("./results", "bounce_results")
        os.makedirs(self.results_dir, exist_ok=True)
        
        # Lock for thread safety
        self.lock = threading.Lock()
        
        # Cache for verification results
        self.result_cache: Dict[str, EmailVerificationResult] = {}
        
        # Tracking for sent emails
        self.sent_emails: Dict[str, Dict[str, Any]] = {}
    
    def verify_email_bounce(self, email: str) -> EmailVerificationResult:
        """
        Verify an email by sending a message and checking for bounces.
        
        Args:
            email: The email address to verify
            
        Returns:
            EmailVerificationResult: The verification result
        """
        logger.info(f"Starting bounce verification for {email}")
        
        # Check if we have SMTP accounts
        if not self.smtp_accounts:
            logger.warning("No SMTP accounts available for bounce verification")
            return EmailVerificationResult(
                email=email,
                category=RISKY,
                reason="No SMTP accounts available for bounce verification",
                provider="bounce"
            )
        
        # Check if email is already in cache
        with self.lock:
            if email in self.result_cache:
                logger.info(f"Using cached bounce verification result for {email}")
                return self.result_cache[email]
        
        # Generate a unique batch ID for this verification
        batch_id = f"bounce_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        
        # Create the results directory
        results_dir = os.path.join(self.results_dir, batch_id)
        os.makedirs(results_dir, exist_ok=True)
        
        # Create email_b.csv file
        self._create_email_file(batch_id, [email])
        
        # Send the email
        sent = self._send_verification_email(email, batch_id)
        if not sent:
            logger.error(f"Failed to send verification email to {email}")
            
            # Update the email status
            self._update_email_status(email, RISKY, batch_id)
            
            result = EmailVerificationResult(
                email=email,
                category=RISKY,
                reason="Failed to send verification email",
                provider="bounce"
            )
            
            with self.lock:
                self.result_cache[email] = result
            
            return result
        
        # Don't wait for bounce backs, just return a pending result
        result = EmailVerificationResult(
            email=email,
            category=RISKY,
            reason="Verification email sent, check bounce backs later",
            provider="bounce"
        )
        
        with self.lock:
            self.result_cache[email] = result
        
        return result
    
    def batch_verify_emails(self, emails: List[str], existing_batch_id: str = None) -> Dict[str, EmailVerificationResult]:
        """
        Verify multiple emails using the bounce method.
        
        Args:
            emails: List of email addresses to verify
            existing_batch_id: Optional existing batch ID to use
            
        Returns:
            Dict[str, EmailVerificationResult]: Dictionary of verification results
        """
        logger.info(f"Starting batch bounce verification for {len(emails)} emails")
        
        # Check if we have SMTP accounts
        if not self.smtp_accounts:
            logger.warning("No SMTP accounts available for bounce verification")
            return {email: EmailVerificationResult(
                email=email,
                category=RISKY,
                reason="No SMTP accounts available for bounce verification",
                provider="bounce"
            ) for email in emails}
        
        # Determine batch ID and directory
        if existing_batch_id:
            batch_id = existing_batch_id
            results_dir = os.path.join("./results", batch_id)
        else:
            # Generate a unique batch ID for this verification
            batch_id = f"bounce_{int(time.time())}_{uuid.uuid4().hex[:8]}"
            results_dir = os.path.join(self.results_dir, batch_id)
        
        # Create the results directory if it doesn't exist
        os.makedirs(results_dir, exist_ok=True)
        
        # Create email_b.csv file
        self._create_email_file(batch_id, emails)
        
        # Create initial status_b.json file
        self._create_status_file(batch_id, emails)
        
        # Send emails
        sent_count = 0
        for email in emails:
            sent = self._send_verification_email(email, batch_id)
            if sent:
                sent_count += 1
                # Update email status
                self._update_email_status(email, PENDING, batch_id)
                # Add a small delay between sends to avoid rate limiting
                time.sleep(random.uniform(0.1, 0.3))
        
        logger.info(f"Sent {sent_count} out of {len(emails)} verification emails for batch {batch_id}")
        
        # Prepare results
        results = {}
        for email in emails:
            results[email] = EmailVerificationResult(
                email=email,
                category=RISKY,
                reason="Verification email sent, check bounce backs later",
                provider="bounce"
            )
            
            # Update cache
            with self.lock:
                self.result_cache[email] = results[email]
        
        return results
    
    # Add new methods for parallel processing and connection pooling

    def batch_verify_emails_parallel(self, emails: List[str], existing_batch_id: str = None) -> Dict[str, EmailVerificationResult]:
        """
        Verify multiple emails using the bounce method with parallel processing.
        
        Args:
            emails: List of email addresses to verify
            existing_batch_id: Optional existing batch ID to use
            
        Returns:
            Dict[str, EmailVerificationResult]: Dictionary of verification results
        """
        logger.info(f"Starting parallel batch bounce verification for {len(emails)} emails")
        
        # Check if we have SMTP accounts
        if not self.smtp_accounts:
            logger.warning("No SMTP accounts available for bounce verification")
            return {email: EmailVerificationResult(
                email=email,
                category=RISKY,
                reason="No SMTP accounts available for bounce verification",
                provider="bounce"
            ) for email in emails}
        
        # Determine batch ID and directory
        if existing_batch_id:
            batch_id = existing_batch_id
            results_dir = os.path.join("./results", batch_id)
        else:
            # Generate a unique batch ID for bounce verification
            batch_id = f"bounce_{int(time.time())}_{uuid.uuid4().hex[:8]}"
            results_dir = os.path.join(self.results_dir, batch_id)
        
        # Create the results directory if it doesn't exist
        os.makedirs(results_dir, exist_ok=True)
        
        # Create email_b.csv file
        self._create_email_file(batch_id, emails)
        
        # Create initial status_b.json file
        self._create_status_file(batch_id, emails)
        
        # Use threading to send emails in parallel
        threads = []
        results_queue = queue.Queue()
        
        # Determine optimal number of threads based on CPU count
        num_threads = min(len(emails), os.cpu_count() * 2)
        emails_per_thread = max(1, len(emails) // num_threads)
        
        # Split emails into chunks for each thread
        email_chunks = []
        for i in range(0, len(emails), emails_per_thread):
            email_chunks.append(emails[i:i+emails_per_thread])
        
        # Create and start threads
        for i, chunk in enumerate(email_chunks):
            thread = threading.Thread(
                target=self._send_emails_thread,
                args=(chunk, batch_id, results_queue)
            )
            thread.daemon = True
            thread.start()
            threads.append(thread)
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Get results from queue
        sent_count = 0
        while not results_queue.empty():
            result = results_queue.get()
            if result:
                sent_count += 1
        
        logger.info(f"Sent {sent_count} out of {len(emails)} verification emails for batch {batch_id}")
        
        # Prepare results
        results = {}
        for email in emails:
            results[email] = EmailVerificationResult(
                email=email,
                category=RISKY,
                reason="Verification email sent, check bounce backs later",
                provider="bounce"
            )
            
            # Update cache
            with self.lock:
                self.result_cache[email] = results[email]
        
        return results

    def _send_emails_thread(self, emails: List[str], batch_id: str, results_queue: queue.Queue) -> None:
        """
        Thread function to send verification emails.
        
        Args:
            emails: List of email addresses to verify
            batch_id: The batch ID
            results_queue: Queue to store results
        """
        # Choose a random SMTP account
        account = random.choice(self.smtp_accounts)
        
        try:
            # Connect to SMTP server once for all emails in this thread
            smtp_server = account.get('smtp_server', '')
            smtp_port = int(account.get('smtp_port', 587))
            
            # Set timeout for SMTP operations - reduced from 30 to 15 seconds
            socket.setdefaulttimeout(15)
            
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.ehlo()
                if smtp_port == 587:
                    server.starttls()
                    server.ehlo()
                
                # Login once
                server.login(account.get('email', ''), account.get('password', ''))
                
                # Send emails
                for email in emails:
                    try:
                        # Create the message
                        msg = MIMEMultipart()
                        msg['From'] = account.get('email', '')
                        msg['To'] = email
                        msg['Subject'] = ""  # Empty subject as requested
                        
                        # Add batch ID to headers for tracking
                        msg['X-Batch-ID'] = batch_id
                        msg['X-Verification-Email'] = email
                        
                        # Create minimal message body
                        body = ""  # Very fast/minimal body as requested
                        msg.attach(MIMEText(body, 'plain'))
                        
                        # Send email
                        server.send_message(msg)
                        
                        logger.info(f"Verification email sent to {email} with batch ID {batch_id}")
                        
                        # Log the sent email
                        self._log_sent_email(email, batch_id, account.get('email', ''))
                        
                        # Update email status
                        self._update_email_status(email, PENDING, batch_id)
                        
                        # Add success to queue
                        results_queue.put(True)
                        
                        # Add a small delay between sends to avoid rate limiting
                        # Reduced from random.uniform(1, 3) to random.uniform(0.1, 0.5)
                        time.sleep(random.uniform(0.1, 0.3))
                        
                    except Exception as e:
                        logger.error(f"Error sending verification email to {email}: {e}")
                        results_queue.put(False)
        
        except Exception as e:
            logger.error(f"Error connecting to SMTP server: {e}")
            # Mark all emails as failed
            for _ in emails:
                results_queue.put(False)

    def process_responses_parallel(self, batch_id: str, save_results: bool = False) -> Tuple[List[str], List[str]]:
        """
        Process responses for a verification batch using parallel processing.
        
        Args:
            batch_id: The batch ID
            save_results: Whether to save the results (default: False)
            
        Returns:
            Tuple[List[str], List[str]]: Lists of invalid and valid emails
        """
        # Get all emails from the batch
        all_emails = self._get_emails_from_batch(batch_id)
        
        # Use threading to check for bounce backs in parallel
        invalid_emails_set = set()
        threads = []
        results_lock = threading.Lock()
        
        # Split accounts for parallel processing
        for account in self.smtp_accounts:
            thread = threading.Thread(
                target=self._check_inbox_thread,
                args=(account, all_emails, invalid_emails_set, results_lock)
            )
            thread.daemon = True
            thread.start()
            threads.append(thread)
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Convert set to list
        invalid_emails = list(invalid_emails_set)
        
        # Emails not in invalid_emails are considered valid
        valid_emails = [email for email in all_emails if email not in invalid_emails_set]
        
        # Update the status file with results only if save_results is True
        if save_results:
            self._update_email_statuses(batch_id, invalid_emails, valid_emails)
            self.save_bounce_results(batch_id, invalid_emails, valid_emails)
        
        return invalid_emails, valid_emails

    def _check_inbox_thread(self, account: Dict[str, Any], all_emails: List[str], 
                           invalid_emails_set: Set[str], results_lock: threading.Lock) -> None:
        """
        Thread function to check inbox for bounce backs.
        
        Args:
            account: SMTP/IMAP account information
            all_emails: List of all emails to check
            invalid_emails_set: Shared set to store invalid emails
            results_lock: Lock for thread safety
        """
        try:
            # Connect to IMAP server
            imap_server = account.get('imap_server', '')
            imap_port = int(account.get('imap_port', 993))
            
            # Set timeout for IMAP operations - reduced from 30 to 15 seconds
            socket.setdefaulttimeout(15)
            
            mail = imaplib.IMAP4_SSL(imap_server, imap_port)
            mail.login(account.get('email', ''), account.get('password', ''))
            mail.select('inbox')
            
            # Use individual search terms instead of combining them
            # This avoids the "BAD [b'Could not parse command']" error
            search_terms = [
                '(FROM "MAILER-DAEMON")',
                '(FROM "Mail Delivery System")',
                '(FROM "postmaster")',
                '(SUBJECT "Undeliverable")',
                '(SUBJECT "Delivery Status Notification")',
                '(SUBJECT "Mail Delivery Failure")',
                '(SUBJECT "Returned mail")',
                '(SUBJECT "Delivery Failure")',
                '(SUBJECT "Failure Notice")'
            ]
            
            search_terms += [
                '(FROM "Microsoft Outlook")',
                '(SUBJECT "Échec de la remise")',
                '(SUBJECT "Delivery Failed")',
            ]
            
            # Process each search term separately
            for search_term in search_terms:
                try:
                    status, messages = mail.search(None, search_term)
                    
                    if status == 'OK' and messages[0]:
                        # Get all message IDs for this search term
                        msg_ids = messages[0].split()
                        
                        # Process messages in batches to improve performance
                        batch_size = 10
                        for i in range(0, len(msg_ids), batch_size):
                            batch_ids = msg_ids[i:i+batch_size]
                            
                            # Fetch multiple messages at once
                            for msg_id in batch_ids:
                                try:
                                    status, msg_data = mail.fetch(msg_id, '(RFC822)')
                                    
                                    if status != 'OK' or not msg_data or not msg_data[0]:
                                        continue
                                    
                                    raw_email = msg_data[0][1]
                                    msg = email.message_from_bytes(raw_email)
                                    
                                    # Extract the body
                                    body = ""
                                    if msg.is_multipart():
                                        for part in msg.walk():
                                            content_type = part.get_content_type()
                                            content_disposition = str(part.get("Content-Disposition"))
                                            
                                            if "attachment" not in content_disposition and content_type in ["text/plain", "text/html"]:
                                                try:
                                                    body_part = part.get_payload(decode=True)
                                                    if body_part:
                                                        body += body_part.decode('utf-8', errors='ignore')
                                                except Exception as e:
                                                    logger.error(f"Error decoding email part: {e}")
                                    else:
                                        try:
                                            body_part = msg.get_payload(decode=True)
                                            if body_part:
                                                body += body_part.decode('utf-8', errors='ignore')
                                        except Exception as e:
                                            logger.error(f"Error decoding email body: {e}")
                                    
                                    # Convert raw_email to string for searching
                                    raw_email_str = str(raw_email)
                                    
                                    # Check if any of our emails are in the bounce message
                                    for email_to_check in all_emails:
                                        if email_to_check in body or email_to_check in raw_email_str:
                                            with results_lock:
                                                invalid_emails_set.add(email_to_check)
                                            # Mark as read
                                            mail.store(msg_id, '+FLAGS', '\\Seen')
                                except Exception as e:
                                    logger.error(f"Error processing message {msg_id}: {e}")
                except Exception as e:
                    logger.error(f"Error with search term '{search_term}': {e}")
            
            # Close connection
            mail.close()
            mail.logout()
            
        except Exception as e:
            logger.error(f"Error checking inbox for {account.get('email', 'unknown')}: {e}")
    
    def _check_inbox_for_bounces(self, batch_id: str) -> Tuple[List[str], List[str]]:
        """
        Check inbox for bounce-back emails.
        
        Args:
            batch_id: The batch ID to look for
            
        Returns:
            Tuple[List[str], List[str]]: Lists of invalid and valid emails
        """
        # Get all emails from the batch
        all_emails = self._get_emails_from_batch(batch_id)
        invalid_emails = []
        
        for account in self.smtp_accounts:
            try:
                # Connect to IMAP server
                imap_server = account.get('imap_server', '')
                imap_port = int(account.get('imap_port', 993))
                
                # Set timeout for IMAP operations
                socket.setdefaulttimeout(15)
                
                mail = imaplib.IMAP4_SSL(imap_server, imap_port)
                mail.login(account.get('email', ''), account.get('password', ''))
                mail.select('inbox')
                
                # Use individual search terms instead of combining them
                search_terms = [
                    '(FROM "MAILER-DAEMON")',
                    '(FROM "Mail Delivery System")',
                    '(FROM "postmaster")',
                    '(SUBJECT "Undeliverable")',
                    '(SUBJECT "Delivery Status Notification")',
                    '(SUBJECT "Mail Delivery Failure")',
                    '(SUBJECT "Returned mail")',
                    '(SUBJECT "Delivery Failure")',
                    '(SUBJECT "Failure Notice")'
                ]
                
                # Process each search term separately
                for search_term in search_terms:
                    try:
                        status, messages = mail.search(None, search_term)
                        
                        if status == 'OK' and messages[0]:
                            # Get all message IDs for this search term
                            msg_ids = messages[0].split()
                            
                            for msg_id in msg_ids:
                                try:
                                    status, msg_data = mail.fetch(msg_id, '(RFC822)')
                                    
                                    if status != 'OK' or not msg_data or not msg_data[0]:
                                        continue
                                    
                                    raw_email = msg_data[0][1]
                                    msg = email.message_from_bytes(raw_email)
                                    
                                    # Extract the body
                                    body = ""
                                    if msg.is_multipart():
                                        for part in msg.walk():
                                            content_type = part.get_content_type()
                                            content_disposition = str(part.get("Content-Disposition"))
                                            
                                            if "attachment" not in content_disposition and content_type in ["text/plain", "text/html"]:
                                                try:
                                                    body_part = part.get_payload(decode=True)
                                                    if body_part:
                                                        body += body_part.decode('utf-8', errors='ignore')
                                                except Exception as e:
                                                    logger.error(f"Error decoding email part: {e}")
                                    else:
                                        try:
                                            body_part = msg.get_payload(decode=True)
                                            if body_part:
                                                body += body_part.decode('utf-8', errors='ignore')
                                        except Exception as e:
                                            logger.error(f"Error decoding email body: {e}")
                                    
                                    # Convert raw_email to string for searching
                                    raw_email_str = str(raw_email)
                                    
                                    # Check if any of our emails are in the bounce message
                                    for email_to_check in all_emails:
                                        if email_to_check in body or email_to_check in raw_email_str:
                                            if email_to_check not in invalid_emails:
                                                invalid_emails.append(email_to_check)
                                            # Mark as read
                                            mail.store(msg_id, '+FLAGS', '\\Seen')
                                except Exception as e:
                                    logger.error(f"Error processing message {msg_id}: {e}")
                    except Exception as e:
                        logger.error(f"Error with search term '{search_term}': {e}")
                
                # Close connection
                mail.close()
                mail.logout()
                
            except Exception as e:
                logger.error(f"Error checking inbox for {account.get('email', 'unknown')}: {e}")
        
        # Emails not in invalid_emails are considered valid
        valid_emails = [email for email in all_emails if email not in invalid_emails]
        
        return invalid_emails, valid_emails
    
    def _create_email_file(self, batch_id: str, emails: List[str]) -> None:
        """
        Create an email_b.csv file for tracking emails.
        
        Args:
            batch_id: The batch ID
            emails: List of email addresses in the batch
        """
        # Determine the correct file path
        if batch_id.startswith("batch_"):
            # Existing batch ID
            file_path = os.path.join("./results", batch_id, "email_b.csv")
        else:
            # New bounce verification
            file_path = os.path.join(self.results_dir, batch_id, "email_b.csv")
        
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            # First line contains the batch ID
            writer.writerow([batch_id])
            
            # Subsequent lines contain email and status
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for email in emails:
                writer.writerow([email, PENDING, timestamp])
                
                # Update tracking
                self.sent_emails[email] = {
                    "batch_id": batch_id,
                    "status": PENDING,
                    "timestamp": timestamp
                }
    
    def _create_status_file(self, batch_id: str, emails: List[str]) -> None:
        """
        Create a status_b.json file for tracking verification status.
        
        Args:
            batch_id: The batch ID
            emails: List of email addresses in the batch
        """
        # Determine the correct file path
        if batch_id.startswith("batch_"):
            # Existing batch ID
            file_path = os.path.join("./results", batch_id, "status_b.json")
        else:
            # New bounce verification
            file_path = os.path.join(self.results_dir, batch_id, "status_b.json")
        
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # Prepare status data
        status_data = {
            "batch_id": batch_id,
            "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "sending",
            "total_emails": len(emails),
            "valid": 0,
            "invalid": 0,
            "risky": len(emails),
            "custom": 0,
            "pending": len(emails),
            "checking_attempts": 0,
            "last_checked": "",
            "first_checked": "",
            "valid_list": [],
            "invalid_list": [],
            "risky_list": emails.copy(),
            "custom_list": []
        }
        
        # Save status data
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(status_data, f, indent=4)
    
    def _update_email_status(self, email: str, status: str, batch_id: str) -> None:
        """
        Update the status of an email in the email_b.csv file.
        
        Args:
            email: The email address
            status: The new status
            batch_id: The batch ID
        """
        # Determine the correct file path
        if batch_id.startswith("batch_"):
            # Existing batch ID
            file_path = os.path.join("./results", batch_id, "email_b.csv")
        else:
            # New bounce verification
            file_path = os.path.join(self.results_dir, batch_id, "email_b.csv")
        
        if not os.path.exists(file_path):
            logger.error(f"Email file {file_path} not found")
            return
        
        # Read the current email file
        rows = []
        with open(file_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            # First row is the batch ID
            batch_id_row = next(reader)
            rows.append(batch_id_row)
            
            for row in reader:
                if len(row) >= 3 and row[0] == email:
                    # Update the status and timestamp
                    row[1] = status
                    row[2] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                rows.append(row)
        
        # Write the updated email file
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            for row in rows:
                writer.writerow(row)
        
        # Update tracking
        if email in self.sent_emails:
            self.sent_emails[email]["status"] = status
            self.sent_emails[email]["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def _log_sent_email(self, email: str, batch_id: str, sender: str) -> None:
        """
        Log a sent email for tracking.
        
        Args:
            email: The recipient email address
            batch_id: The batch ID
            sender: The sender email address
        """
        try:
            # Determine the correct log file location based on batch_id
            if batch_id.startswith("batch_"):
                # Existing batch ID
                log_dir = os.path.join("./results", batch_id)
            else:
                # New bounce verification
                log_dir = os.path.join(self.results_dir, batch_id)
            
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, "sent_emails.log")
            
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"{timestamp},{email},{batch_id},{sender}\n")
        except Exception as e:
            logger.error(f"Error logging sent email: {e}")
    
    def _get_emails_from_batch(self, batch_id: str) -> List[str]:
        """
        Get all emails that were part of a verification batch.
        
        Args:
            batch_id: The batch ID
            
        Returns:
            List[str]: List of email addresses in the batch
        """
        emails = []
        
        # Determine the correct file path
        if batch_id.startswith("batch_"):
            # Existing batch ID
            file_path = os.path.join("./results", batch_id, "email_b.csv")
        else:
            # New bounce verification
            file_path = os.path.join(self.results_dir, batch_id, "email_b.csv")
        
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', newline='', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    next(reader)  # Skip first line (batch ID)
                    
                    for row in reader:
                        if row and len(row) >= 1:
                            emails.append(row[0])
            except Exception as e:
                logger.error(f"Error reading email file {file_path}: {e}")
        
        # If no emails found in email file, check the sent emails log
        if not emails:
            try:
                # Determine the correct log file location
                if batch_id.startswith("batch_"):
                    # Existing batch ID
                    log_file = os.path.join("./results", batch_id, "sent_emails.log")
                else:
                    # New bounce verification
                    log_file = os.path.join(self.results_dir, batch_id, "sent_emails.log")
                
                if os.path.exists(log_file):
                    with open(log_file, 'r', encoding='utf-8') as f:
                        for line in f:
                            parts = line.strip().split(',')
                            if len(parts) >= 2:
                                emails.append(parts[1])
            except Exception as e:
                logger.error(f"Error reading sent emails log: {e}")
        
        return emails
    
    def get_all_batches(self) -> List[Dict[str, Any]]:
        """
        Get information about all verification batches.
        
        Returns:
            List[Dict[str, Any]]: List of batch information dictionaries
        """
        batches = []
        
        try:
            # Check results directory for batch folders
            results_dir = "./results"
            if os.path.exists(results_dir):
                for item in os.listdir(results_dir):
                    item_path = os.path.join(results_dir, item)
                    # Look for batch folders (starting with "batch_")
                    if os.path.isdir(item_path) and (item.startswith("batch_") or item.startswith("bounce_")):
                        batch_id = item
                        
                        # Get batch statistics if available
                        status_file = os.path.join(item_path, "status.json")
                        status_b_file = os.path.join(item_path, "status_b.json")
                        email_b_file = os.path.join(item_path, "email_b.csv")
                        
                        # Only include if it has email_b.csv or status_b.json or it's a batch_ folder
                        if item.startswith("batch_") or os.path.exists(email_b_file) or os.path.exists(status_b_file):
                            created_time = ""
                            total_emails = 0
                            valid_count = 0
                            invalid_count = 0
                            risky_count = 0
                            custom_count = 0
                            pending_count = 0
                            status = "Unknown"
                            
                            if os.path.exists(status_file):
                                try:
                                    with open(status_file, 'r', encoding='utf-8') as f:
                                        status_data = json.load(f)
                                        created_time = status_data.get("start_time", "")
                                        total_emails = status_data.get("total_emails", 0)
                                        valid_count = status_data.get("results", {}).get("valid", 0)
                                        invalid_count = status_data.get("results", {}).get("invalid", 0)
                                        risky_count = status_data.get("results", {}).get("risky", 0)
                                        custom_count = status_data.get("results", {}).get("custom", 0)
                                        pending_count = total_emails - (valid_count + invalid_count + risky_count + custom_count)
                                except Exception as e:
                                    logger.error(f"Error reading status file for {batch_id}: {e}")
                            
                            # Check if there's a bounce status file
                            if os.path.exists(status_b_file):
                                try:
                                    with open(status_b_file, 'r', encoding='utf-8') as f:
                                        status_b_data = json.load(f)
                                        if not created_time:
                                            created_time = status_b_data.get("created", "")
                                        if total_emails == 0:
                                            total_emails = status_b_data.get("total_emails", 0)
                                        valid_count = status_b_data.get("valid", 0)
                                        invalid_count = status_b_data.get("invalid", 0)
                                        risky_count = status_b_data.get("risky", 0)
                                        custom_count = status_b_data.get("custom", 0)
                                        pending_count = status_b_data.get("pending", 0)
                                        status = status_b_data.get("status", "Pending")
                                except Exception as e:
                                    logger.error(f"Error reading status_b file for {batch_id}: {e}")
                            
                            batches.append({
                                "batch_id": batch_id,
                                "created": created_time,
                                "total_emails": total_emails,
                                "valid": valid_count,
                                "invalid": invalid_count,
                                "risky": risky_count,
                                "custom": custom_count,
                                "pending": pending_count,
                                "status": status
                            })
            
            # Also check bounce_results directory
            bounce_results_dir = os.path.join("./results", "bounce_results")
            if os.path.exists(bounce_results_dir):
                for item in os.listdir(bounce_results_dir):
                    item_path = os.path.join(bounce_results_dir, item)
                    if os.path.isdir(item_path) and item.startswith("bounce_"):
                        batch_id = item
                        
                        # Get batch statistics if available
                        status_b_file = os.path.join(item_path, "status_b.json")
                        email_b_file = os.path.join(item_path, "email_b.csv")
                        
                        # Only include if it has email_b.csv or status_b.json
                        if os.path.exists(email_b_file) or os.path.exists(status_b_file):
                            created_time = ""
                            total_emails = 0
                            valid_count = 0
                            invalid_count = 0
                            risky_count = 0
                            custom_count = 0
                            pending_count = 0
                            status = "Unknown"
                            
                            if os.path.exists(status_b_file):
                                try:
                                    with open(status_b_file, 'r', encoding='utf-8') as f:
                                        status_b_data = json.load(f)
                                        created_time = status_b_data.get("created", "")
                                        total_emails = status_b_data.get("total_emails", 0)
                                        valid_count = status_b_data.get("valid", 0)
                                        invalid_count = status_b_data.get("invalid", 0)
                                        risky_count = status_b_data.get("risky", 0)
                                        custom_count = status_b_data.get("custom", 0)
                                        pending_count = status_b_data.get("pending", 0)
                                        status = status_b_data.get("status", "Pending")
                                except Exception as e:
                                    logger.error(f"Error reading status_b file for {batch_id}: {e}")
                            
                            batches.append({
                                "batch_id": batch_id,
                                "created": created_time,
                                "total_emails": total_emails,
                                "valid": valid_count,
                                "invalid": invalid_count,
                                "risky": risky_count,
                                "custom": custom_count,
                                "pending": pending_count,
                                "status": status
                            })
        except Exception as e:
            logger.error(f"Error getting batch information: {e}")
        
        # Sort batches by creation time (newest first)
        batches.sort(key=lambda x: x["created"] if x["created"] else "", reverse=True)
        
        return batches
    
    def process_responses(self, batch_id: str, save_results: bool = False) -> Tuple[List[str], List[str]]:
        """
        Process responses for a verification batch.
        
        Args:
            batch_id: The batch ID
            save_results: Whether to save the results (default: False)
            
        Returns:
            Tuple[List[str], List[str]]: Lists of invalid and valid emails
        """
        # Check for bounce-backs
        invalid_emails, valid_emails = self._check_inbox_for_bounces(batch_id)
        
        # Update the status file with results only if save_results is True
        if save_results:
            self._update_email_statuses(batch_id, invalid_emails, valid_emails)
            self.save_bounce_results(batch_id, invalid_emails, valid_emails)
        
        return invalid_emails, valid_emails
    
    def _update_email_statuses(self, batch_id: str, invalid_emails: List[str], valid_emails: List[str]) -> None:
        """
        Update the status of emails in the email_b.csv file.
        
        Args:
            batch_id: The batch ID
            invalid_emails: List of invalid email addresses
            valid_emails: List of valid email addresses
        """
        # Determine the correct file path
        if batch_id.startswith("batch_"):
            # Existing batch ID
            file_path = os.path.join("./results", batch_id, "email_b.csv")
        else:
            # New bounce verification
            file_path = os.path.join(self.results_dir, batch_id, "email_b.csv")
        
        if not os.path.exists(file_path):
            logger.error(f"Email file {file_path} not found")
            return
        
        # Read the current email file
        rows = []
        with open(file_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            # First row is the batch ID
            batch_id_row = next(reader)
            rows.append(batch_id_row)
            
            for row in reader:
                if len(row) >= 3:
                    email = row[0]
                    
                    if email in invalid_emails:
                        row[1] = INVALID
                    elif email in valid_emails:
                        row[1] = VALID
                    
                    # Update timestamp
                    row[2] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                rows.append(row)
        
        # Write the updated email file
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            for row in rows:
                writer.writerow(row)
    
    def get_emails_by_reason(self, reason_filter: List[str] = None) -> List[str]:
        """
        Get emails from results files filtered by reason.
        
        Args:
            reason_filter: List of reason substrings to filter by
            
        Returns:
            List[str]: List of email addresses matching the filter
        """
        if not reason_filter:
            return []
        
        emails = []
        
        # Check invalid results file
        results_file = os.path.join("./results", "invalid.csv")
        if os.path.exists(results_file):
            try:
                with open(results_file, 'r', newline='', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    next(reader)  # Skip header
                    
                    for row in reader:
                        if len(row) >= 4:  # Email, Provider, Timestamp, Reason
                            email = row[0]
                            reason = row[3]
                            
                            # Check if reason matches any filter
                            if any(filter_text.lower() in reason.lower() for filter_text in reason_filter):
                                emails.append(email)
            except Exception as e:
                logger.error(f"Error reading invalid results file: {e}")
        
        return emails
    
    def get_unique_reasons(self, batch_id: str = None) -> Dict[str, List[str]]:
        """
        Get unique reasons from invalid emails, optionally filtered by batch ID.
        
        Args:
            batch_id: Optional batch ID to filter by
            
        Returns:
            Dict[str, List[str]]: Dictionary mapping reasons to lists of emails
        """
        reason_to_emails = {}
        
        try:
            # Check the invalid results file
            results_file = os.path.join("./results", "invalid.csv")
            
            if os.path.exists(results_file):
                with open(results_file, 'r', newline='', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    next(reader)  # Skip header
                    
                    for row in reader:
                        if len(row) >= 6:  # Ensure we have all columns
                            email = row[0]
                            reason = row[3] if row[3] else "Unknown"
                            row_batch_id = row[5] if len(row) > 5 else ""
                            
                            # Filter by batch ID if provided
                            if batch_id and row_batch_id != batch_id:
                                continue
                            
                            if reason not in reason_to_emails:
                                reason_to_emails[reason] = []
                            
                            reason_to_emails[reason].append(email)
            
            return reason_to_emails
        except Exception as e:
            logger.error(f"Error getting unique reasons: {e}")
            return {}
    
    def save_bounce_results(self, batch_id: str, invalid_emails: List[str], valid_emails: List[str]) -> None:
        """
        Save bounce verification results to the correct location.
        
        Args:
            batch_id: The batch ID
            invalid_emails: List of invalid email addresses
            valid_emails: List of valid email addresses
        """
        try:
            # Determine the correct save location based on batch_id
            if batch_id.startswith("batch_"):
                # Case 1: Existing batch ID
                results_dir = os.path.join("./results", batch_id)
            else:
                # Case 2: New generated ID
                results_dir = os.path.join("./results/bounce_results", batch_id)
            
            os.makedirs(results_dir, exist_ok=True)
            
            # Get all emails from the batch
            all_emails = self._get_emails_from_batch(batch_id)
            
            # Determine risky emails (not in valid or invalid)
            risky_emails = [email for email in all_emails if email not in valid_emails and email not in invalid_emails]
            
            # Get existing status data if available
            status_file = os.path.join(results_dir, "status_b.json")
            status_data = {}
            
            if os.path.exists(status_file):
                try:
                    with open(status_file, 'r', encoding='utf-8') as f:
                        status_data = json.load(f)
                except Exception as e:
                    logger.error(f"Error reading status file {status_file}: {e}")
            
            # Update status data
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            if not status_data:
                # Create new status data
                status_data = {
                    "batch_id": batch_id,
                    "created": now,
                    "status": "checked",
                    "total_emails": len(all_emails),
                    "valid": len(valid_emails),
                    "invalid": len(invalid_emails),
                    "risky": len(risky_emails),
                    "custom": 0,
                    "pending": len(risky_emails),
                    "checking_attempts": 1,
                    "last_checked": now,
                    "first_checked": now,
                    "valid_list": valid_emails,
                    "invalid_list": invalid_emails,
                    "risky_list": risky_emails,
                    "custom_list": []
                }
            else:
                # Update existing status data
                status_data["status"] = "checked"
                status_data["checking_attempts"] = status_data.get("checking_attempts", 0) + 1
                status_data["last_checked"] = now
                
                if "first_checked" not in status_data:
                    status_data["first_checked"] = now
                
                # Update lists based on checking attempts and time elapsed
                checking_attempts = status_data.get("checking_attempts", 0)
                first_checked_str = status_data.get("first_checked", "")
                
                # Parse first checked time
                first_checked_time = None
                if first_checked_str:
                    try:
                        first_checked_time = datetime.strptime(first_checked_str, "%Y-%m-%d %H:%M:%S")
                    except Exception as e:
                        logger.error(f"Error parsing first_checked time: {e}")
                
                # Calculate time elapsed since first check
                time_elapsed = None
                if first_checked_time:
                    time_elapsed = datetime.now() - first_checked_time
                
                # Update lists based on checking attempts and time elapsed
                if checking_attempts >= 3 or (time_elapsed and time_elapsed > timedelta(hours=24)):
                    # Third try or more than 24 hours: emails without bounce backs are valid
                    status_data["valid"] = len(valid_emails)
                    status_data["invalid"] = len(invalid_emails)
                    status_data["risky"] = 0
                    status_data["pending"] = 0
                    status_data["valid_list"] = valid_emails
                    status_data["invalid_list"] = invalid_emails
                    status_data["risky_list"] = []
                else:
                    # First or second try: emails with bounce backs are invalid, others stay risky
                    status_data["valid"] = 0
                    status_data["invalid"] = len(invalid_emails)
                    status_data["risky"] = len(risky_emails)
                    status_data["pending"] = len(risky_emails)
                    status_data["valid_list"] = []
                    status_data["invalid_list"] = invalid_emails
                    status_data["risky_list"] = risky_emails
                
                # Log the current status after update
                logger.info(f"Results for batch {batch_id}: Valid emails: {status_data['valid']}, Invalid emails: {status_data['invalid']}, Risky emails: {status_data['risky']}")

            # Save status data
            with open(status_file, 'w', encoding='utf-8') as f:
                json.dump(status_data, f, indent=4)
            
            logger.info(f"Bounce results saved to {status_file}")
            
        except Exception as e:
            logger.error(f"Error saving bounce results: {e}")
    
    def get_emails_by_batch_id(self, batch_id: str, category: str) -> List[str]:
        """
        Get emails from a specific batch and category.
        
        Args:
            batch_id: The batch ID
            category: The category (valid, invalid, risky, custom)
            
        Returns:
            List[str]: List of email addresses
        """
        emails = []
        
        try:
            # Check the results file for the category
            results_file = os.path.join("./results", f"{category}.csv")
            
            if os.path.exists(results_file):
                with open(results_file, 'r', newline='', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    next(reader)  # Skip header
                    
                    for row in reader:
                        if len(row) >= 6 and row[5] == batch_id:  # BatchID is in column 5
                            emails.append(row[0])  # Email is in column 0
            
            return emails
        except Exception as e:
            logger.error(f"Error getting emails for batch {batch_id} and category {category}: {e}")
            return []
