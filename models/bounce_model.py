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
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple, Set

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
        self.batches_dir = os.path.join("./data", "bounce_batches")
        self.results_dir = os.path.join("./data", "bounce_results")
        os.makedirs(self.batches_dir, exist_ok=True)
        os.makedirs(self.results_dir, exist_ok=True)
        
        # Lock for thread safety
        self.lock = threading.Lock()
        
        # Cache for verification results
        self.result_cache: Dict[str, EmailVerificationResult] = {}
        
        # Tracking for sent emails
        self.sent_emails: Dict[str, Dict[str, Any]] = {}
        
        # Load any existing batches
        self._load_existing_batches()
    
    def _load_existing_batches(self) -> None:
        """Load existing batch information from files."""
        try:
            for filename in os.listdir(self.batches_dir):
                if filename.endswith(".csv"):
                    batch_id = os.path.splitext(filename)[0]
                    batch_file = os.path.join(self.batches_dir, filename)
                    
                    with open(batch_file, 'r', newline='', encoding='utf-8') as f:
                        reader = csv.reader(f)
                        header = next(reader)  # Skip header
                        
                        for row in reader:
                            if len(row) >= 3:
                                email = row[0]
                                status = row[1]
                                timestamp = row[2]
                                
                                self.sent_emails[email] = {
                                    "batch_id": batch_id,
                                    "status": status,
                                    "timestamp": timestamp
                                }
        except Exception as e:
            logger.error(f"Error loading existing batches: {e}")
    
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
        
        # Check if email is already in a batch
        if email in self.sent_emails:
            batch_info = self.sent_emails[email]
            batch_id = batch_info["batch_id"]
            status = batch_info["status"]
            
            # If the email has already been verified, return the result
            if status in [VALID, INVALID]:
                logger.info(f"Email {email} already verified as {status} in batch {batch_id}")
                result = EmailVerificationResult(
                    email=email,
                    category=status,
                    reason=f"Email previously verified as {status} in batch {batch_id}",
                    provider="bounce"
                )
                
                with self.lock:
                    self.result_cache[email] = result
                
                return result
            
            # If the email is pending, check for bounces
            if status == PENDING:
                logger.info(f"Email {email} is pending in batch {batch_id}, checking for bounces")
                invalid_emails, valid_emails = self._check_inbox_for_bounces(batch_id)
                
                # Update the batch file with results
                self._save_results(invalid_emails, valid_emails, batch_id)
                
                # Return the result
                if email in invalid_emails:
                    result = EmailVerificationResult(
                        email=email,
                        category=INVALID,
                        reason="Email bounced back as invalid",
                        provider="bounce"
                    )
                elif email in valid_emails:
                    result = EmailVerificationResult(
                        email=email,
                        category=VALID,
                        reason="Email delivered successfully",
                        provider="bounce"
                    )
                else:
                    result = EmailVerificationResult(
                        email=email,
                        category=RISKY,
                        reason="No bounce received, but delivery status uncertain",
                        provider="bounce"
                    )
                
                with self.lock:
                    self.result_cache[email] = result
                
                return result
        
        # Generate a unique batch ID for this verification
        batch_id = f"bounce_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        
        # Create a batch file
        self._create_batch_file(batch_id, [email])
        
        # Send the email
        sent = self._send_verification_email(email, batch_id)
        if not sent:
            logger.error(f"Failed to send verification email to {email}")
            
            # Update the batch file
            self._update_batch_status(email, RISKY, batch_id)
            
            result = EmailVerificationResult(
                email=email,
                category=RISKY,
                reason="Failed to send verification email",
                provider="bounce"
            )
            
            with self.lock:
                self.result_cache[email] = result
            
            return result
        
        # Wait for potential bounce-backs
        wait_time = self.settings_model.get_int("bounce_wait_time", 60)
        logger.info(f"Waiting {wait_time} seconds for potential bounce-backs...")
        time.sleep(wait_time)
        
        # Check for bounce-backs
        invalid_emails, valid_emails = self._check_inbox_for_bounces(batch_id)
        
        # Update the batch file with results
        self._save_results(invalid_emails, valid_emails, batch_id)
        
        # Determine the result
        if email in invalid_emails:
            result = EmailVerificationResult(
                email=email,
                category=INVALID,
                reason="Email bounced back as invalid",
                provider="bounce"
            )
        elif email in valid_emails:
            result = EmailVerificationResult(
                email=email,
                category=VALID,
                reason="Email delivered successfully",
                provider="bounce"
            )
        else:
            # No bounce received, assume valid but mark as risky
            result = EmailVerificationResult(
                email=email,
                category=RISKY,
                reason="No bounce received, but delivery status uncertain",
                provider="bounce"
            )
        
        with self.lock:
            self.result_cache[email] = result
        
        return result
    
    def batch_verify_emails(self, emails: List[str]) -> Dict[str, EmailVerificationResult]:
        """
        Verify multiple emails using the bounce method.
        
        Args:
            emails: List of email addresses to verify
            
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
        
        # Generate a unique batch ID for this verification
        batch_id = f"bounce_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        
        # Create a batch file
        self._create_batch_file(batch_id, emails)
        
        # Send emails
        sent_count = 0
        for email in emails:
            sent = self._send_verification_email(email, batch_id)
            if sent:
                sent_count += 1
                # Add a small delay between sends to avoid rate limiting
                time.sleep(random.uniform(1, 3))
        
        logger.info(f"Sent {sent_count} out of {len(emails)} verification emails for batch {batch_id}")
        
        # Wait for potential bounce-backs
        wait_time = self.settings_model.get_int("bounce_wait_time", 60)
        logger.info(f"Waiting {wait_time} seconds for potential bounce-backs...")
        time.sleep(wait_time)
        
        # Check for bounce-backs
        invalid_emails, valid_emails = self._check_inbox_for_bounces(batch_id)
        
        # Update the batch file with results
        self._save_results(invalid_emails, valid_emails, batch_id)
        
        # Prepare results
        results = {}
        for email in emails:
            if email in invalid_emails:
                results[email] = EmailVerificationResult(
                    email=email,
                    category=INVALID,
                    reason="Email bounced back as invalid",
                    provider="bounce"
                )
            elif email in valid_emails:
                results[email] = EmailVerificationResult(
                    email=email,
                    category=VALID,
                    reason="Email delivered successfully",
                    provider="bounce"
                )
            else:
                # No bounce received, assume valid but mark as risky
                results[email] = EmailVerificationResult(
                    email=email,
                    category=RISKY,
                    reason="No bounce received, but delivery status uncertain",
                    provider="bounce"
                )
            
            # Update cache
            with self.lock:
                self.result_cache[email] = results[email]
        
        return results
    
    def _create_batch_file(self, batch_id: str, emails: List[str]) -> None:
        """
        Create a batch file for tracking verification status.
        
        Args:
            batch_id: The batch ID
            emails: List of email addresses in the batch
        """
        batch_file = os.path.join(self.batches_dir, f"{batch_id}.csv")
        
        with open(batch_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["email", "status", "timestamp"])
            
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for email in emails:
                writer.writerow([email, PENDING, timestamp])
                
                # Update tracking
                self.sent_emails[email] = {
                    "batch_id": batch_id,
                    "status": PENDING,
                    "timestamp": timestamp
                }
    
    def _update_batch_status(self, email: str, status: str, batch_id: str) -> None:
        """
        Update the status of an email in a batch file.
        
        Args:
            email: The email address
            status: The new status
            batch_id: The batch ID
        """
        batch_file = os.path.join(self.batches_dir, f"{batch_id}.csv")
        
        if not os.path.exists(batch_file):
            logger.error(f"Batch file {batch_file} not found")
            return
        
        # Read the current batch file
        rows = []
        with open(batch_file, 'r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader)
            rows.append(header)
            
            for row in reader:
                if len(row) >= 3 and row[0] == email:
                    # Update the status and timestamp
                    row[1] = status
                    row[2] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                rows.append(row)
        
        # Write the updated batch file
        with open(batch_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            for row in rows:
                writer.writerow(row)
        
        # Update tracking
        if email in self.sent_emails:
            self.sent_emails[email]["status"] = status
            self.sent_emails[email]["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def _send_verification_email(self, recipient_email: str, batch_id: str) -> bool:
        """
        Send a verification email to the recipient.
        
        Args:
            recipient_email: The email address to verify
            batch_id: A unique ID for this verification batch
            
        Returns:
            bool: True if the email was sent successfully, False otherwise
        """
        # Choose a random SMTP account
        account = random.choice(self.smtp_accounts)
        
        try:
            # Create the message
            msg = MIMEMultipart()
            msg['From'] = account.get('email', '')
            msg['To'] = recipient_email
            msg['Subject'] = f"Email Verification - {batch_id}"
            
            # Add batch ID to headers for tracking
            msg['X-Batch-ID'] = batch_id
            msg['X-Verification-Email'] = recipient_email
            
            # Create message body
            body = f"""
            This is an automated email verification message.
            Please ignore this message.
            
            Verification ID: {batch_id}
            """
            msg.attach(MIMEText(body, 'plain'))
            
            # Connect to SMTP server
            smtp_server = account.get('smtp_server', '')
            smtp_port = int(account.get('smtp_port', 587))
            
            # Set timeout for SMTP operations
            socket.setdefaulttimeout(30)
            
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.ehlo()
                if smtp_port == 587:
                    server.starttls()
                    server.ehlo()
                
                # Login
                server.login(account.get('email', ''), account.get('password', ''))
                
                # Send email
                server.send_message(msg)
                
                logger.info(f"Verification email sent to {recipient_email} with batch ID {batch_id}")
                
                # Log the sent email
                self._log_sent_email(recipient_email, batch_id, account.get('email', ''))
                
                return True
                
        except Exception as e:
            logger.error(f"Error sending verification email to {recipient_email}: {e}")
            return False
    
    def _log_sent_email(self, email: str, batch_id: str, sender: str) -> None:
        """
        Log a sent email for tracking.
        
        Args:
            email: The recipient email address
            batch_id: The batch ID
            sender: The sender email address
        """
        try:
            log_file = os.path.join("./data", "sent_emails.log")
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"{timestamp},{email},{batch_id},{sender}\n")
        except Exception as e:
            logger.error(f"Error logging sent email: {e}")
    
    def _check_inbox_for_bounces(self, batch_id: str) -> Tuple[List[str], List[str]]:
        """
        Check inbox for bounce-back emails.
        
        Args:
            batch_id: The batch ID to look for
            
        Returns:
            Tuple[List[str], List[str]]: Lists of invalid and valid emails
        """
        invalid_emails = []
        
        for account in self.smtp_accounts:
            try:
                # Connect to IMAP server
                imap_server = account.get('imap_server', '')
                imap_port = int(account.get('imap_port', 993))
                
                # Set timeout for IMAP operations
                socket.setdefaulttimeout(30)
                
                mail = imaplib.IMAP4_SSL(imap_server, imap_port)
                mail.login(account.get('email', ''), account.get('password', ''))
                mail.select('inbox')
                
                # Search for bounce emails
                account_invalid_emails = []
                
                # Search for emails with the batch ID in headers
                status, messages = mail.search(None, f'(HEADER X-Batch-ID "{batch_id}")')
                
                if status == 'OK' and messages[0]:
                    for msg_id in messages[0].split():
                        status, msg_data = mail.fetch(msg_id, '(RFC822)')
                        
                        if status != 'OK':
                            continue
                        
                        raw_email = msg_data[0][1]
                        msg = email.message_from_bytes(raw_email)
                        
                        # Check if this is a delivery status notification
                        if 'delivery status notification' in msg.get('Subject', '').lower() or \
                           'undeliverable' in msg.get('Subject', '').lower() or \
                           'failed delivery' in msg.get('Subject', '').lower() or \
                           'mail delivery failed' in msg.get('Subject', '').lower() or \
                           'returned mail' in msg.get('Subject', '').lower() or \
                           'delivery failure' in msg.get('Subject', '').lower() or \
                           'delivery status' in msg.get('Subject', '').lower() or \
                           'failure notice' in msg.get('Subject', '').lower() or \
                           'mail delivery notification' in msg.get('Subject', '').lower():
                            
                            # Extract the body
                            body = ""
                            if msg.is_multipart():
                                for part in msg.walk():
                                    content_type = part.get_content_type()
                                    content_disposition = str(part.get("Content-Disposition"))
                                    
                                    if "attachment" not in content_disposition and content_type in ["text/plain", "text/html"]:
                                        try:
                                            body_part = part.get_payload(decode=True).decode()
                                            body += body_part
                                        except:
                                            pass
                            else:
                                try:
                                    body = msg.get_payload(decode=True).decode()
                                except:
                                    pass
                            
                            # Extract invalid email from the body
                            invalid_email = self._extract_invalid_email_from_bounce(body, str(raw_email))
                            
                            if invalid_email:
                                account_invalid_emails.append(invalid_email)
                            
                            # Mark as read
                            mail.store(msg_id, '+FLAGS', '\\Seen')
                
                # Also search for bounce emails in the subject
                search_terms = [
                    '(SUBJECT "delivery status notification")',
                    '(SUBJECT "undeliverable")',
                    '(SUBJECT "failed delivery")',
                    '(SUBJECT "mail delivery failed")',
                    '(SUBJECT "returned mail")',
                    '(SUBJECT "delivery failure")',
                    '(SUBJECT "delivery status")',
                    '(SUBJECT "failure notice")',
                    '(SUBJECT "mail delivery notification")'
                ]
                
                for search_term in search_terms:
                    status, messages = mail.search(None, search_term)
                    
                    if status == 'OK' and messages[0]:
                        for msg_id in messages[0].split():
                            status, msg_data = mail.fetch(msg_id, '(RFC822)')
                            
                            if status != 'OK':
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
                                            body_part = part.get_payload(decode=True).decode()
                                            body += body_part
                                        except:
                                            pass
                            else:
                                try:
                                    body = msg.get_payload(decode=True).decode()
                                except:
                                    pass
                            
                            # Check if the body contains the batch ID
                            if batch_id in body:
                                # Extract invalid email from the body
                                invalid_email = self._extract_invalid_email_from_bounce(body, str(raw_email))
                                
                                if invalid_email:
                                    account_invalid_emails.append(invalid_email)
                                
                                # Mark as read
                                mail.store(msg_id, '+FLAGS', '\\Seen')
                
                # Add invalid emails from this account
                invalid_emails.extend(account_invalid_emails)
                
                # Close connection
                mail.close()
                mail.logout()
                
            except Exception as e:
                logger.error(f"Error checking inbox for {account.get('email', 'unknown')}: {e}")
        
        # Get list of all emails in the batch
        all_emails = self._get_emails_from_batch(batch_id)
        
        # Emails not in invalid_emails are considered valid
        valid_emails = [email for email in all_emails if email not in invalid_emails]
        
        return invalid_emails, valid_emails
    
    def _extract_invalid_email_from_bounce(self, body: str, raw_email: str) -> Optional[str]:
        """
        Extract the invalid email address from a bounce message.
        
        Args:
            body: The body of the bounce message
            raw_email: The raw email content
            
        Returns:
            str or None: The invalid email address, or None if not found
        """
        # Common patterns for invalid emails in bounce messages
        patterns = [
            r'(?:failed for|failed recipient|failed address|unknown user|user unknown|user not found|no such user|recipient rejected|does not exist|invalid recipient|undeliverable to|not exist|not found|rejected recipient|recipient address rejected|mailbox unavailable|mailbox not found|no mailbox|address rejected|address not found|address does not exist|no such recipient|recipient does not exist|recipient unknown|unknown recipient|recipient not found|recipient no longer|recipient address no longer|user doesn\'t have|user does not have|no such account|account does not exist|account not found|account unavailable|account closed|account disabled|account suspended|account terminated|account deleted|account removed|account blocked|account locked|account inactive|account expired|account cancelled|account canceled|account deactivated|account discontinued|account rejected|account invalid|account not available|account not active|account not valid|account not recognized|account not accepted|account not allowed|account not permitted|account not authorized|account not authenticated|account not verified|account not confirmed|account not approved|account not enabled|account not accessible|account not reachable|account not deliverable|account not routable|account not routeable|account not routed|account not delivered|account not forwarded|account not relayed|account not sent|account not transmitted|account not transferred|account not transported|account not conveyed|account not dispatched|account not distributed|account not directed|account not addressed|account not mailed|account not emailed|account not messaged|account not communicated|account not contacted|account not reached|account not connected|account not linked|account not associated|account not related|account not affiliated|account not bound|account not tied|account not coupled|account not joined|account not united|account not attached|account not fixed|account not secured|account not fastened|account not anchored|account not moored|account not tethered|account not chained|account not roped|account not cabled|account not wired|account not corded|account not stringed|account not threaded|account not strung|account not laced|account not tied|account not knotted|account not looped|account not hooked|account not latched|account not locked|account not bolted|account not screwed|account not nailed|account not pinned|account not stapled|account not riveted|account not welded|account not soldered|account not glued|account not cemented|account not bonded|account not adhered|account not stuck|account not pasted|account not taped|account not tacked|account not thumbtacked|account not pushpinned|account not paperclipped|account not clipped|account not clamped|account not gripped|account not grasped|account not clutched|account not held|account not kept|account not maintained|account not preserved|account not retained|account not sustained|account not supported|account not upheld|account not propped|account not backed|account not braced|account not buttressed|account not reinforced|account not strengthened|account not fortified|account not bolstered|account not boosted|account not elevated|account not lifted|account not raised|account not hoisted|account not heightened|account not increased|account not enhanced|account not augmented|account not amplified|account not magnified|account not intensified|account not escalated|account not inflated|account not expanded|account not enlarged|account not extended|account not stretched|account not lengthened|account not widened|account not broadened|account not deepened|account not thickened|account not fattened|account not swelled|account not distended|account not bloated|account not puffed|account not ballooned|account not inflated|account not blown|account not pumped|account not filled|account not loaded|account not packed|account not stuffed|account not crammed|account not jammed|account not squeezed|account not pressed|account not pushed|account not shoved|account not thrust|account not forced|account not driven|account not propelled|account not impelled|account not urged|account not compelled|account not obliged|account not required|account not needed|account not wanted|account not desired|account not wished|account not requested|account not asked|account not demanded|account not ordered|account not commanded|account not directed|account not instructed|account not told|account not advised|account not counseled|account not guided|account not led|account not steered|account not piloted|account not navigated|account not conducted|account not escorted|account not accompanied|account not attended|account not chaperoned|account not guarded|account not protected|account not defended|account not shielded|account not sheltered|account not covered|account not screened|account not masked|account not disguised|account not hidden|account not concealed|account not veiled|account not cloaked|account not shrouded|account not obscured|account not camouflaged|account not buried|account not interred|account not entombed|account not inhumed|account not planted|account not sown|account not seeded|account not germinated|account not sprouted|account not budded|account not bloomed|account not blossomed|account not flowered|account not fruited|account not ripened|account not matured|account not developed|account not grown|account not evolved|account not progressed|account not advanced|account not proceeded|account not moved|account not shifted|account not transferred|account not relocated|account not displaced|account not repositioned|account not rearranged|account not reordered|account not reorganized|account not restructured|account not reconfigured|account not reformed|account not reshaped|account not remolded|account not remodeled|account not renovated|account not refurbished|account not refitted|account not rehabilitated|account not restored|account not revived|account not revitalized|account not rejuvenated|account not renewed|account not refreshed|account not replenished|account not restocked|account not resupplied|account not refilled|account not reloaded|account not repacked|account not restuffed|account not recrammed|account not rejammed|account not resqueezed|account not repressed|account not repushed|account not reshoved|account not rethrust|account not reforced|account not redriven|account not repropelled|account not reimpelled|account not reurged|account not recompelled|account not reobliged|account not rerequired|account not reneeded|account not rewanted|account not redesired|account not rewished|account not rerequested|account not reasked|account not redemanded|account not reordered|account not recommanded|account not redirected|account not reinstructed|account not retold|account not readvised|account not recounseled|account not reguided|account not reled|account not resteered|account not repiloted|account not renavigated|account not reconducted|account not reescorted|account not reaccompanied|account not reattended|account not rechaperoned|account not reguarded|account not reprotected|account not redefended|account not reshielded|account not resheltered|account not recovered|account not rescreened|account not remasked|account not redisguised|account not rehidden|account not reconcealed|account not reveiled|account not recloaked|account not reshrouded|account not reobscured|account not recamouflaged|account not reburied|account not reinterred|account not reentombed|account not reinhumed|account not replanted|account not resown|account not reseeded|account not regerminated|account not resprouted|account not rebudded|account not rebloomed|account not reblossomed|account not reflowered|account not refruited|account not reripened|account not rematured|account not redeveloped|account not regrown|account not reevolved|account not reprogressed|account not readvanced|account not reproceeded|account not removed|account not reshifted|account not retransferred|account not rerelocated|account not redisplaced|account not repositioned|account not rerearranged|account not rereordered|account not rereorganized|account not rerestructured|account not rereconfigured|account not rereformed|account not rereshaped|account not reremolded|account not reremodeled|account not rerenovated|account not rerefurbished|account not rerefitted|account not rerehabilitatedaccount not rerestored|account not rerevived|account not rerevitalized|account not rerejuvenated|account not rerenewed|account not rerefreshed|account not rereplenished|account not rerestocked|account not reresupplied|account not rerefilled|account not rereloaded|account not rerepacked|account not rerestuffed|account not rerecrammed|account not rerejammed|account not reresqueezed|account not rerepressed|account not rerepushed|account not rereshoved|account not rerethrust|account not rereforced|account not reredriven|account not rerepropelled|account not rereimpelled|account not rereurged|account not rerecompelled|account not rereobliged|account not rererequired|account not rereneeded|account not rerewanted|account not reredesired|account not rerewished|account not rererequested|account not rereasked|account not reredemanded|account not rereordered|account not rerecommanded|account not reredirected|account not rereinstructed|account not reretold|account not rereadvised|account not rerecounseled|account not rereguided|account not rereled|account not reresteered|account not rerepiloted|account not rerenavigated|account not rereconducted|account not rereescorted|account not rereaccompanied|account not rereattended|account not rerechaperoned|account not rereguarded|account not rereprotected|account not reredefended|account not rereshielded|account not reresheltered|account not rerecovered|account not rerescreened|account not reremasked|account not reredisguised|account not rerehidden|account not rereconcealed|account not rerevelied|account not rerecloaked|account not rereshrouded|account not rereobscured|account not rerecamouflaged|account not rereburied|account not rereinterred|account not rereentombed|account not rereinhumed|account not rereplanted|account not reresown|account not rereseeded|account not reregerminated|account not reresprouted|account not rerebudded|account not rerebloomed|account not rereblossomed|account not rereflowered|account not rerefruited|account not rereripened|account not rerematured|account not reredeveloped|account not reregrown|account not rereevolved|account not rereprogressed|account not rereadvanced|account not rereproceeded|account not reremoved|account not rereshifted|account not reretransferred|account not rererelocated|account not reredisplaced|account not rerepositione):[\s\n]*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
            r'(?:failed for|failed recipient|failed address|unknown user|user unknown|user not found|no such user|recipient rejected|does not exist|invalid recipient|undeliverable to|not exist|not found|rejected recipient|recipient address rejected|mailbox unavailable|mailbox not found|no mailbox|address rejected|address not found|address does not exist|no such recipient|recipient does not exist|recipient unknown|unknown recipient|recipient not found|recipient no longer|recipient address no longer|user doesn\'t have|user does not have|no such account|account does not exist|account not found|account unavailable|account closed|account disabled|account suspended|account terminated|account deleted|account removed|account blocked|account locked|account inactive|account expired|account cancelled|account canceled|account deactivated|account discontinued|account rejected|account invalid|account not available|account not active|account not valid|account not recognized|account not accepted|account not allowed|account not permitted|account not authorized|account not authenticated|account not verified|account not confirmed|account not approved|account not enabled|account not accessible|account not reachable|account not deliverable|account not routable|account not routeable|account not routed|account not delivered|account not forwarded|account not relayed|account not sent|account not transmitted|account not transferred|account not transported|account not conveyed|account not dispatched|account not distributed|account not directed|account not addressed|account not mailed|account not emailed|account not messaged|account not communicated|account not contacted|account not reached|account not connected|account not linked|account not associated|account not related|account not affiliated|account not bound|account not tied|account not coupled|account not joined|account not united|account not attached|account not fixed|account not secured|account not fastened|account not anchored|account not moored|account not tethered|account not chained|account not roped|account not cabled|account not wired|account not corded|account not stringed|account not threaded|account not strung|account not laced|account not tied|account not knotted|account not looped|account not hooked|account not latched|account not locked|account not bolted|account not screwed|account not nailed|account not pinned|account not stapled|account not riveted|account not welded|account not soldered|account not glued|account not cemented|account not bonded|account not adhered|account not stuck|account not pasted|account not taped|account not tacked|account not thumbtacked|account not pushpinned|account not paperclipped|account not clipped|account not clamped|account not gripped|account not grasped|account not clutched|account not held|account not kept|account not maintained|account not preserved|account not retained|account not sustained|account not supported|account not upheld|account not propped|account not backed|account not braced|account not buttressed|account not reinforced|account not strengthened|account not fortified|account not bolstered|account not boosted|account not elevated|account not lifted|account not raised|account not hoisted|account not heightened|account not increased|account not enhanced|account not augmented|account not amplified|account not magnified|account not intensified|account not escalated|account not inflated|account not expanded|account not enlarged|account not extended|account not stretched|account not lengthened|account not widened|account not broadened|account not deepened|account not thickened|account not fattened|account not swelled|account not distended|account not bloated|account not puffed|account not ballooned|account not inflated|account not blown|account not pumped|account not filled|account not loaded|account not packed|account not stuffed|account not crammed|account not jammed|account not squeezed|account not pressed|account not pushed|account not shoved|account not thrust|account not forced|account not driven|account not propelled|account not impelled|account not urged|account not compelled|account not obliged|account not required|account not needed|account not wanted|account not desired|account not wished|account not requested|account not asked|account not demanded|account not ordered|account not commanded|account not directed|account not instructed|account not told|account not advised|account not counseled|account not guided|account not led|account not steered|account not piloted|account not navigated|account not conducted|account not escorted|account not accompanied|account not attended|account not chaperoned|account not guarded|account not protected|account not defended|account not shielded|account not sheltered|account not covered|account not screened|account not masked|account not disguised|account not hidden|account not concealed|account not veiled|account not cloaked|account not shrouded|account not obscured|account not camouflaged|account not buried|account not interred|account not entombed|account not inhumed|account not planted|account not sown|account not seeded|account not germinated|account not sprouted|account not budded|account not bloomed|account not blossomed|account not flowered|account not fruited|account not ripened|account not matured|account not developed|account not grown|account not evolved|account not progressed|account not advanced|account not proceeded|account not moved|account not shifted|account not transferred|account not relocated|account not displaced|account not repositioned|account not rearranged|account not reordered|account not reorganized|account not restructured|account not reconfigured|account not reformed|account not reshaped|account not remolded|account not remodeled|account not renovated|account not refurbished|account not refitted|account not rehabilitatedaccount not rerestored|account not rerevived|account not rerevitalized|account not rerejuvenated|account not rerenewed|account not rerefreshed|account not rereplenished|account not rerestocked|account not reresupplied|account not rerefilled|account not rereloaded|account not rerepacked|account not rerestuffed|account not rerecrammed|account not rerejammed|account not reresqueezed|account not rerepressed|account not rerepushed|account not rereshoved|account not rerethrust|account not rereforced|account not reredriven|account not rerepropelled|account not rereimpelled|account not rereurged|account not rerecompelled|account not rereobliged|account not rererequired|account not rereneeded|account not rerewanted|account not reredesired|account not rerewished|account not rererequested|account not rereasked|account not reredemanded|account not rereordered|account not rerecommanded|account not reredirected|account not rereinstructed|account not reretold|account not rereadvised|account not rerecounseled|account not rereguided|account not rereled|account not reresteered|account not rerepiloted|account not rerenavigated|account not rereconducted|account not rereescorted|account not rereaccompanied|account not rereattended|account not rerechaperoned|account not rereguarded|account not rereprotected|account not reredefended|account not rereshielded|account not reresheltered|account not rerecovered|account not rerescreened|account not reremasked|account not reredisguised|account not rerehidden|account not rereconcealed|account not rerevelied|account not rerecloaked|account not rereshrouded|account not rereobscured|account not rerecamouflaged|account not rereburied|account not rereinterred|account not rereentombed|account not rereinhumed|account not rereplanted|account not reresown|account not rereseeded|account not reregerminated|account not reresprouted|account not rerebudded|account not rerebloomed|account not rereblossomed|account not rereflowered|account not rerefruited|account not rereripened|account not rerematured|account not reredeveloped|account not reregrown|account not rereevolved|account not rereprogressed|account not rereadvanced|account not rereproceeded|account not reremoved|account not rereshifted|account not reretransferred|account not rererelocated|account not reredisplaced|account not rerepositione).*?([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
            r'(?:failed for|failed recipient|failed address|unknown user|user unknown|user not found|no such user|recipient rejected|does not exist|invalid recipient|undeliverable to|not exist|not found|rejected recipient|recipient address rejected|mailbox unavailable|mailbox not found|no mailbox|address rejected|address not found|address does not exist|no such recipient|recipient does not exist|recipient unknown|unknown recipient|recipient not found|recipient no longer|recipient address no longer|user doesn\'t have|user does not have|no such account|account does not exist|account not found|account unavailable|account closed|account disabled|account suspended|account terminated|account deleted|account removed|account blocked|account locked|account inactive|account expired|account cancelled|account canceled|account deactivated|account discontinued|account rejected|account invalid|account not available|account not active|account not valid|account not recognized|account not accepted|account not allowed|account not permitted|account not authorized|account not authenticated|account not verified|account not confirmed|account not approved|account not enabled|account not accessible|account not reachable|account not deliverable|account not routable|account not routeable|account not routed|account not delivered|account not forwarded|account not relayed|account not sent|account not transmitted|account not transferred|account not transported|account not conveyed|account not dispatched|account not distributed|account not directed|account not addressed|account not mailed|account not emailed|account not messaged|account not communicated|account not contacted|account not reached|account not connected|account not linked|account not associated|account not related|account not affiliated|account not bound|account not tied|account not coupled|account not joined|account not united|account not attached|account not fixed|account not secured|account not fastened|account not anchored|account not moored|account not tethered|account not chained|account not roped|account not cabled|account not wired|account not corded|account not stringed|account not threaded|account not strung|account not laced|account not tied|account not knotted|account not looped|account not hooked|account not latched|account not locked|account not bolted|account not screwed|account not nailed|account not pinned|account not stapled|account not riveted|account not welded|account not soldered|account not glued|account not cemented|account not bonded|account not adhered|account not stuck|account not pasted|account not taped|account not tacked|account not thumbtacked|account not pushpinned|account not paperclipped|account not clipped|account not clamped|account not gripped|account not grasped|account not clutched|account not held|account not kept|account not maintained|account not preserved|account not retained|account not sustained|account not supported|account not upheld|account not propped|account not backed|account not braced|account not buttressed|account not reinforced|account not strengthened|account not fortified|account not bolstered|account not boosted|account not elevated|account not lifted|account not raised|account not hoisted|account not heightened|account not increased|account not enhanced|account not augmented|account not amplified|account not magnified|account not intensified|account not escalated|account not inflated|account not expanded|account not enlarged|account not extended|account not stretched|account not lengthened|account not widened|account not broadened|account not deepened|account not thickened|account not fattened|account not swelled|account not distended|account not bloated|account not puffed|account not ballooned|account not inflated|account not blown|account not pumped|account not filled|account not loaded|account not packed|account not stuffed|account not crammed|account not jammed|account not squeezed|account not pressed|account not pushed|account not shoved|account not thrust|account not forced|account not driven|account not propelled|account not impelled|account not urged|account not compelled|account not obliged|account not required|account not needed|account not wanted|account not desired|account not wished|account not requested|account not asked|account not demanded|account not ordered|account not commanded|account not directed|account not instructed|account not told|account not advised|account not counseled|account not guided|account not led|account not steered|account not piloted|account not navigated|account not conducted|account not escorted|account not accompanied|account not attended|account not chaperoned|account not guarded|account not protected|account not defended|account not shielded|account not sheltered|account not covered|account not screened|account not masked|account not disguised|account not hidden|account not concealed|account not veiled|account not cloaked|account not shrouded|account not obscured|account not camouflaged|account not buried|account not interred|account not entombed|account not inhumed|account not planted|account not sown|account not seeded|account not germinated|account not sprouted|account not budded|account not bloomed|account not blossomed|account not flowered|account not fruited|account not ripened|account not matured|account not developed|account not grown|account not evolved|account not progressed|account not advanced|account not proceeded|account not moved|account not shifted|account not transferred|account not relocated|account not displaced|account not repositioned|account not rearranged|account not reordered|account not reorganized|account not restructured|account not reconfigured|account not reformed|account not reshaped|account not remolded|account not remodeled|account not renovated|account not refurbished|account not refitted|account not rehabilitated|account not restored|account not revived|account not revitalized|account not rejuvenated|account not renewed|account not refreshed|account not replenished|account not restocked|account not resupplied|account not refilled|account not reloaded|account not repacked|account not restuffed|account not recrammed|account not rejammed|account not resqueezed|account not repressed|account not repushed|account not reshoved|account not rethrust|account not reforced|account not redriven|account not repropelled|account not reimpelled|account not reurged|account not recompelled|account not reobliged|account not rerequired|account not reneeded|account not rewanted|account not redesired|account not rewished|account not rerequested|account not reasked|account not reredemanded|account not rereordered|account not rerecommanded|account not reredirected|account not rereinstructed|account not reretold|account not rereadvised|account not rerecounseled|account not rereguided|account not rereled|account not reresteered|account not rerepiloted|account not rerenavigated|account not rereconducted|account not rereescorted|account not rereaccompanied|account not rereattended|account not rerechaperoned|account not rereguarded|account not rereprotected|account not reredefended|account not rereshielded|account not reresheltered|account not rerecovered|account not rerescreened|account not reremasked|account not reredisguised|account not rerehidden|account not rereconcealed|account not rerevelied|account not rerecloaked|account not rereshrouded|account not rereobscured|account not rerecamouflaged|account not rereburied|account not rereinterred|account not rereentombed|account not rereinhumed|account not rereplanted|account not reresown|account not rereseeded|account not reregerminated|account not reresprouted|account not rerebudded|account not rerebloomed|account not rereblossomed|account not rereflowered|account not rerefruited|account not rereripened|account not rerematured|account not reredeveloped|account not reregrown|account not rereevolved|account not rereprogressed|account not rereadvanced|account not rereproceeded|account not reremoved|account not rereshifted|account not reretransferred|account not rererelocated|account not reredisplaced|account not rerepositione).*?([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
            r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}).*?(?:failed|undeliverable|unknown|not found|does not exist|invalid|rejected|unavailable|no mailbox|no such|not exist|not active|disabled|suspended|terminated|deleted|removed|blocked|locked|inactive|expired|cancelled|canceled|deactivated|discontinued)',
            r'Original-Recipient:.*?([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
            r'Final-Recipient:.*?([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
            r'X-Failed-Recipients:.*?([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, body, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1)
        
        # If no match found in body, try the raw email
        for pattern in patterns:
            match = re.search(pattern, raw_email, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1)
        
        return None
    
    def _get_emails_from_batch(self, batch_id: str) -> List[str]:
        """
        Get all emails that were part of a verification batch.
        
        Args:
            batch_id: The batch ID
            
        Returns:
            List[str]: List of email addresses in the batch
        """
        emails = []
        
        # Check the batch file
        batch_file = os.path.join(self.batches_dir, f"{batch_id}.csv")
        
        if os.path.exists(batch_file):
            try:
                with open(batch_file, 'r', newline='', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    next(reader)  # Skip header
                    
                    for row in reader:
                        if row and len(row) >= 1:
                            emails.append(row[0])
            except Exception as e:
                logger.error(f"Error reading batch file {batch_file}: {e}")
        
        # If no emails found in batch file, check the sent emails log
        if not emails:
            try:
                log_file = os.path.join("./data", "sent_emails.log")
                
                if os.path.exists(log_file):
                    with open(log_file, 'r', encoding='utf-8') as f:
                        for line in f:
                            if batch_id in line:
                                parts = line.strip().split(',')
                                if len(parts) >= 2:
                                    emails.append(parts[1])
            except Exception as e:
                logger.error(f"Error reading sent emails log: {e}")
        
        return emails
    
    def _save_results(self, invalid_emails: List[str], valid_emails: List[str], batch_id: str) -> None:
        """
        Save verification results to files.
        
        Args:
            invalid_emails: List of invalid email addresses
            valid_emails: List of valid email addresses
            batch_id: The batch ID
        """
        # Update the batch file
        batch_file = os.path.join(self.batches_dir, f"{batch_id}.csv")
        
        if os.path.exists(batch_file):
            try:
                # Read the current batch file
                rows = []
                with open(batch_file, 'r', newline='', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    header = next(reader)
                    rows.append(header)
                    
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
                
                # Write the updated batch file
                with open(batch_file, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    for row in rows:
                        writer.writerow(row)
                
                # Update tracking
                for email in invalid_emails:
                    if email in self.sent_emails:
                        self.sent_emails[email]["status"] = INVALID
                        self.sent_emails[email]["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                for email in valid_emails:
                    if email in self.sent_emails:
                        self.sent_emails[email]["status"] = VALID
                        self.sent_emails[email]["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
            except Exception as e:
                logger.error(f"Error updating batch file {batch_file}: {e}")
        
        # Save results to separate files
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        
        # Save invalid emails
        if invalid_emails:
            invalid_file = os.path.join(self.results_dir, f"{batch_id}_invalid_{timestamp}.csv")
            
            with open(invalid_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(["email", "batch_id", "timestamp", "reason"])
                
                for email in invalid_emails:
                    writer.writerow([email, batch_id, timestamp, "Email bounced back as invalid"])
        
        # Save valid emails
        if valid_emails:
            valid_file = os.path.join(self.results_dir, f"{batch_id}_valid_{timestamp}.csv")
            
            with open(valid_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(["email", "batch_id", "timestamp", "reason"])
                
                for email in valid_emails:
                    writer.writerow([email, batch_id, timestamp, "No bounce-back received"])
    
    def get_all_batches(self) -> List[Dict[str, Any]]:
        """
        Get information about all verification batches.
        
        Returns:
            List[Dict[str, Any]]: List of batch information dictionaries
        """
        batches = []
        
        try:
            for filename in os.listdir(self.batches_dir):
                if filename.endswith(".csv"):
                    batch_id = os.path.splitext(filename)[0]
                    batch_file = os.path.join(self.batches_dir, filename)
                    
                    # Get batch statistics
                    total_emails = 0
                    valid_count = 0
                    invalid_count = 0
                    pending_count = 0
                    created_time = ""
                    
                    with open(batch_file, 'r', newline='', encoding='utf-8') as f:
                        reader = csv.reader(f)
                        next(reader)  # Skip header
                        
                        for row in reader:
                            if len(row) >= 3:
                                total_emails += 1
                                
                                if row[1] == VALID:
                                    valid_count += 1
                                elif row[1] == INVALID:
                                    invalid_count += 1
                                elif row[1] == PENDING:
                                    pending_count += 1
                                
                                if not created_time and row[2]:
                                    created_time = row[2]
                    
                    batches.append({
                        "batch_id": batch_id,
                        "created": created_time,
                        "total_emails": total_emails,
                        "valid": valid_count,
                        "invalid": invalid_count,
                        "pending": pending_count,
                        "status": "Completed" if pending_count == 0 else "Waiting for checking"
                    })
        except Exception as e:
            logger.error(f"Error getting batch information: {e}")
        
        # Sort batches by creation time (newest first)
        batches.sort(key=lambda x: x["created"], reverse=True)
        
        return batches
    
    def process_responses(self, batch_id: str) -> Tuple[int, int]:
        """
        Process responses for a verification batch.
        
        Args:
            batch_id: The batch ID
            
        Returns:
            Tuple[int, int]: Count of invalid and valid emails
        """
        # Check for bounce-backs
        invalid_emails, valid_emails = self._check_inbox_for_bounces(batch_id)
        
        # Update the batch file with results
        self._save_results(invalid_emails, valid_emails, batch_id)
        
        return len(invalid_emails), len(valid_emails)

