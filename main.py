#!/usr/bin/env python3
import os
import sys
import logging
import argparse
import csv
from typing import Dict, List, Any, Optional
import time
import uuid
import random
import json

# Import all models
from models.settings_model import SettingsModel
from models.initial_validation_model import InitialValidationModel
from models.smtp_model import SMTPModel
from models.selenium_model import SeleniumModel
from models.api_model import APIModel
from models.sequence_model import SequenceModel
from models.judgment_model import JudgmentModel
from models.multi_terminal_model import MultiTerminalModel
from models.results_model import ResultsModel
from models.statistics_model import StatisticsModel
from models.bounce_model import BounceModel
from models.controller import VerificationController

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.FileHandler("email_verifier.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def create_required_directories():
    """Create all required directories for the application."""
    directories = [
        "./data",
        "./results",
        "./screenshots",
        "./statistics",
        "./statistics/history",
        "./results/bounce_results"
    ]
    
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
    
    # Create required data files if they don't exist
    data_files = [
        "D-blacklist.csv",
        "D-WhiteList.csv",
        "Valid.csv",
        "Invalid.csv",
        "Risky.csv",
        "Custom.csv"
    ]
    
    for file in data_files:
        file_path = os.path.join("./data", file)
        if not os.path.exists(file_path):
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                if file in ["D-blacklist.csv", "D-WhiteList.csv"]:
                    f.write("domain\n")
                else:
                    f.write("email\n")

def main_menu():
    """Display the main menu and handle user input."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Email Verification System')
    parser.add_argument('--job-id', type=str, help='Job ID for batch verification')
    parser.add_argument('--terminal', type=int, help='Terminal ID for multi-terminal mode')
    parser.add_argument('--emails', type=str, help='Path to file containing emails to verify')
    args = parser.parse_args()
    
    # Initialize the controller
    controller = VerificationController()
    
    # Initialize the bounce model
    bounce_model = BounceModel(controller.settings_model)
    
    # Check if running in terminal mode with emails file
    if args.terminal and args.emails:
        # Read emails from file
        emails = []
        try:
            with open(args.emails, 'r', encoding='utf-8') as f:
                for line in f:
                    email = line.strip()
                    if '@' in email:  # Basic validation
                        emails.append(email)
        except Exception as e:
            logger.error(f"Error reading emails file: {e}")
            sys.exit(1)
        
        # Verify emails
        logger.info(f"Terminal {args.terminal} verifying {len(emails)} emails")
        
        for email in emails:
            try:
                # Verify email
                result = controller.verify_email(email)
                
                # Print result for parsing by parent process
                print(f"RESULT:{email}:{result.category}")
                
                # If job_id is provided, save result to job directory
                if args.job_id:
                    controller.results_model.save_result(result, args.job_id)
                
            except Exception as e:
                logger.error(f"Error verifying {email}: {e}")
                print(f"RESULT:{email}:risky")
        
        logger.info(f"Terminal {args.terminal} completed")
        sys.exit(0)
    
    # Normal interactive mode
    while True:
        print("\nEmail Verification System")
        print("========================")
        print("1. Verify a single email")
        print("2. Verify multiple emails")
        print("3. Bounce verification")
        print("4. Show results summary")
        print("5. Show detailed statistics")
        print("6. Settings")
        print("7. Exit")
        
        choice = input("\nEnter your choice (1-7): ")
        
        if choice == "1":
            email = input("\nEnter an email to verify: ")
            print(f"\nVerifying {email}...")
            result = controller.verify_email(email)
            print(f"\nResult: {result}")
            
        elif choice == "2":
            controller.batch_verification_menu()
            
        elif choice == "3":
            bounce_verification_menu(bounce_model, controller)
            
        elif choice == "4":
            controller.show_results_summary()
            
        elif choice == "5":
            controller.show_statistics_menu()
            
        elif choice == "6":
            controller.settings_menu()
            
        elif choice == "7":
            print("\nExiting Email Verification System. Goodbye!")
            break
            
        else:
            print("\nInvalid choice. Please try again.")

def bounce_verification_menu(bounce_model, controller):
    """Display the bounce verification menu and handle user input."""
    while True:
        print("\nBounce Verification:")
        print("1. Verify bulk of emails")
        print("2. Verify risky emails")
        print("3. Verify invalid emails")
        print("4. Check for bounce back")
        print("5. Return to main menu")
        
        choice = input("\nEnter your choice (1-5): ")
        
        if choice == "1":
            print("\nVerify bulk of emails:")
            print("1. Enter manually")
            print("2. Enter CSV file")
            print("3. Verify batch ID")
            
            bulk_choice = input("\nEnter your choice (1-3): ")
            
            if bulk_choice == "1":
                # Enter manually
                emails_input = input("\nEnter emails separated by commas: ")
                emails = [email.strip() for email in emails_input.split(",") if '@' in email.strip()]
                
                if not emails:
                    print("\nNo valid emails provided.")
                    continue
                
                # Generate a unique batch ID for bounce verification
                batch_id = f"bounce_{int(time.time())}_{uuid.uuid4().hex[:8]}"
                
                print(f"\nSending verification emails to {len(emails)} emails...")
                
                # Send verification emails without waiting for bounce backs
                # Use parallel processing for better performance
                results = bounce_model.batch_verify_emails_parallel(emails)
                
                print(f"\nVerification emails sent. You can check for bounce backs later using option 4 (Check for bounce back)")
                
            elif bulk_choice == "2":
                # Load from CSV
                file_path = input("\nEnter the path to the CSV file: ")
                try:
                    emails = []
                    with open(file_path, 'r') as f:
                        for line in f:
                            email = line.strip()
                            if '@' in email:  # Basic validation
                                emails.append(email)
                    
                    if not emails:
                        print("\nNo valid emails found in the file.")
                        continue
                    
                    # Generate a unique batch ID for bounce verification
                    batch_id = f"bounce_{int(time.time())}_{uuid.uuid4().hex[:8]}"
                    
                    print(f"\nSending verification emails to {len(emails)} emails...")
                    
                    # Send verification emails without waiting for bounce backs
                    # Use parallel processing for better performance
                    results = bounce_model.batch_verify_emails_parallel(emails)
                    
                    print(f"\nVerification emails sent. You can check for bounce backs later using option 4 (Check for bounce back)")
                    
                except Exception as e:
                    print(f"\nError reading file: {e}")
                    continue
                
            elif bulk_choice == "3":
                # Verify batch ID
                batches = bounce_model.get_all_batches()
                
                if not batches:
                    print("\nNo batches found.")
                    continue
                
                print("\nAvailable batches:")
                for i, batch in enumerate(batches, 1):
                    print(f"{i}. {batch['batch_id']} - {batch['created']} - {batch['total_emails']} emails ({batch['valid']} valid, {batch['invalid']} invalid, {batch['risky']} risky, {batch['custom']} custom, {batch['pending']} pending)")
                
                batch_choice = input("\nEnter batch number to verify: ")
                try:
                    batch_index = int(batch_choice) - 1
                    if 0 <= batch_index < len(batches):
                        batch_id = batches[batch_index]["batch_id"]
                        
                        print("\nChoose verification type:")
                        print("1. Verify risky emails")
                        print("2. Verify invalid emails")
                        
                        verify_type = input("\nEnter your choice (1-2): ")
                        
                        if verify_type == "1":
                            # Verify risky emails from this batch
                            risky_emails = bounce_model.get_emails_by_batch_id(batch_id, "risky")
                            
                            if not risky_emails:
                                print(f"\nNo risky emails found for batch {batch_id}.")
                                continue
                            
                            print(f"\nFound {len(risky_emails)} risky emails for batch {batch_id}.")
                            verify_all = input("Verify these emails? (y/n): ")
                            
                            if verify_all.lower() == 'y':
                                print(f"\nSending verification emails to {len(risky_emails)} risky emails...")
                                
                                # Send verification emails using the existing batch ID
                                # Use parallel processing for better performance
                                results = bounce_model.batch_verify_emails_parallel(risky_emails, batch_id)
                                
                                print(f"\nVerification emails sent. You can check for bounce backs later using option 4 (Check for bounce back)")
                            else:
                                print("\nOperation cancelled.")
                        
                        elif verify_type == "2":
                            # Verify invalid emails from this batch
                            reason_to_emails = bounce_model.get_unique_reasons(batch_id)
                            
                            if not reason_to_emails:
                                print(f"\nNo invalid emails found for batch {batch_id}.")
                                continue
                            
                            print("\nInvalid email reasons:")
                            reasons = list(reason_to_emails.keys())
                            for i, reason in enumerate(reasons, 1):
                                print(f"{i}. \"{reason}\": {len(reason_to_emails[reason])}")
                            
                            reason_choice = input("\nEnter reason number to verify: ")
                            try:
                                reason_index = int(reason_choice) - 1
                                if 0 <= reason_index < len(reasons):
                                    selected_reason = reasons[reason_index]
                                    invalid_emails = reason_to_emails[selected_reason]
                                    
                                    print(f"\nFound {len(invalid_emails)} emails with reason \"{selected_reason}\".")
                                    verify_all = input("Verify these emails? (y/n): ")
                                    
                                    if verify_all.lower() == 'y':
                                        print(f"\nSending verification emails to {len(invalid_emails)} invalid emails...")
                                        
                                        # Send verification emails using the existing batch ID
                                        # Use parallel processing for better performance
                                        results = bounce_model.batch_verify_emails_parallel(invalid_emails, batch_id)
                                        
                                        print(f"\nVerification emails sent. You can check for bounce backs later using option 4 (Check for bounce back)")
                                    else:
                                        print("\nOperation cancelled.")
                                else:
                                    print("\nInvalid reason number.")
                            except ValueError:
                                print("\nInvalid input. Please enter a number.")
                        else:
                            print("\nInvalid choice.")
                    else:
                        print("\nInvalid batch number.")
                except ValueError:
                    print("\nInvalid input. Please enter a number.")
        
        elif choice == "2":
            # Verify risky emails
            print("\nVerifying risky emails using bounce method...")
            
            # Get risky emails from results file
            risky_emails = []
            results_file = os.path.join("./results", "risky.csv")
            
            if os.path.exists(results_file):
                try:
                    with open(results_file, 'r', newline='', encoding='utf-8') as f:
                        reader = csv.reader(f)
                        next(reader)  # Skip header
                        
                        for row in reader:
                            if row and len(row) >= 1:
                                risky_emails.append(row[0])
                except Exception as e:
                    print(f"\nError reading risky emails: {e}")
                    continue
            
            if not risky_emails:
                print("\nNo risky emails found.")
                continue
            
            print(f"\nFound {len(risky_emails)} risky emails.")
            verify_all = input("Verify all risky emails? (y/n): ")
            
            if verify_all.lower() == 'y':
                # Generate a unique batch ID for bounce verification
                batch_id = f"bounce_{int(time.time())}_{uuid.uuid4().hex[:8]}"
                
                print(f"\nSending verification emails to {len(risky_emails)} risky emails...")
                
                # Send verification emails without waiting for bounce backs
                # Use parallel processing for better performance
                results = bounce_model.batch_verify_emails_parallel(risky_emails)
                
                print(f"\nVerification emails sent. You can check for bounce backs later using option 4 (Check for bounce back)")
            else:
                print("\nOperation cancelled.")
        
        elif choice == "3":
            # Verify invalid emails
            print("\nVerifying invalid emails using bounce method...")
            
            # Get invalid reasons
            reason_to_emails = bounce_model.get_unique_reasons()
            
            if not reason_to_emails:
                print("\nNo invalid emails found.")
                continue
            
            print("\nInvalid email reasons:")
            reasons = list(reason_to_emails.keys())
            for i, reason in enumerate(reasons, 1):
                print(f"{i}. \"{reason}\": {len(reason_to_emails[reason])}")
            
            reason_choice = input("\nEnter reason number to verify: ")
            try:
                reason_index = int(reason_choice) - 1
                if 0 <= reason_index < len(reasons):
                    selected_reason = reasons[reason_index]
                    invalid_emails = reason_to_emails[selected_reason]
                    
                    print(f"\nFound {len(invalid_emails)} emails with reason \"{selected_reason}\".")
                    verify_all = input("Verify these emails? (y/n): ")
                    
                    if verify_all.lower() == 'y':
                        # Generate a unique batch ID for bounce verification
                        batch_id = f"bounce_{int(time.time())}_{uuid.uuid4().hex[:8]}"
                        
                        print(f"\nSending verification emails to {len(invalid_emails)} invalid emails...")
                        
                        # Send verification emails without waiting for bounce backs
                        # Use parallel processing for better performance
                        results = bounce_model.batch_verify_emails_parallel(invalid_emails)
                        
                        print(f"\nVerification emails sent. You can check for bounce backs later using option 4 (Check for bounce back)")
                    else:
                        print("\nOperation cancelled.")
                else:
                    print("\nInvalid reason number.")
            except ValueError:
                print("\nInvalid input. Please enter a number.")
        
        elif choice == "4":
            # Check for bounce back
            print("\nCheck for bounce back:")
            
            # Get all bounce batches
            batches = bounce_model.get_all_batches()
            
            if not batches:
                print("\nNo bounce verification batches found.")
                continue
            
            print("\nAvailable batches:")
            for i, batch in enumerate(batches, 1):
                print(f"{i}. {batch['batch_id']} - Status: {batch['status']}")
            
            batch_choice = input("\nEnter batch ID number to check: ")
            try:
                batch_index = int(batch_choice) - 1
                if 0 <= batch_index < len(batches):
                    batch_id = batches[batch_index]["batch_id"]
                    
                    # Show current status
                    current_status = batches[batch_index]["status"]
                    print(f"\nCurrent status for batch {batch_id}: {current_status}")
                    
                    continue_check = input("Continue with checking bounce backs? (y/n): ")
                    if continue_check.lower() != 'y':
                        print("\nOperation cancelled.")
                        continue
                    
                    print(f"\nChecking bounce backs for batch {batch_id}...")
                    # Use parallel processing for faster bounce checking
                    invalid_emails, valid_emails = bounce_model.process_responses_parallel(batch_id, save_results=False)
                    
                    print(f"\nResults for batch {batch_id}:")
                    print(f"Valid emails: {len(valid_emails)}")
                    print(f"Invalid emails: {len(invalid_emails)}")
                    
                    if invalid_emails:
                        print("\nInvalid emails:")
                        for email in invalid_emails:
                            print(f"- {email}")
                    
                    save_results = input("\nDo you want to save these results? (y/n): ")
                    if save_results.lower() == 'y':
                        # Process again with save_results=True
                        bounce_model.process_responses_parallel(batch_id, save_results=True)
                        print("\nResults saved successfully.")
                    else:
                        print("\nResults not saved.")
                else:
                    print("\nInvalid batch number.")
            except ValueError:
                print("\nInvalid input. Please enter a number.")
        
        elif choice == "5":
            # Return to main menu
            break
        
        else:
            print("\nInvalid choice. Please try again.")

if __name__ == "__main__":
    # Create required directories
    create_required_directories()
    
    # Start the application
    main_menu()

