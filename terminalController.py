import os
import csv
import sys
import time
import subprocess
import threading
import argparse
import random
import datetime
import shutil
from typing import List, Dict, Any

def create_directory(directory: str) -> None:
    """Create directory if it doesn't exist."""
    if not os.path.exists(directory):
        os.makedirs(directory)

def divide_emails(csv_path: str, num_terminals: int) -> List[str]:
    """
    Divide emails from a CSV file into chunks for each terminal.
    
    Args:
        csv_path: Path to the CSV file containing emails
        num_terminals: Number of terminals to divide emails among
        
    Returns:
        List[str]: List of paths to the chunked CSV files
    """
    # Create terminal directory and files subdirectory if they don't exist
    terminal_dir = "terminal"
    files_dir = os.path.join(terminal_dir, "files")
    create_directory(terminal_dir)
    create_directory(files_dir)
    
    # Read emails from CSV file
    emails = []
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            # Read all lines
            lines = f.readlines()
            
            # Check if first line is a header
            first_line = lines[0].strip() if lines else ""
            start_idx = 0
            
            if first_line and ('@' not in first_line or first_line.lower() == "email" or 
                              "email" in first_line.lower() or "mail" == first_line.lower()):
                print(f"Detected header: '{first_line}' - skipping this line")
                start_idx = 1
            
            # Process all non-header lines
            for i in range(start_idx, len(lines)):
                email = lines[i].strip()
                if '@' in email:  # Basic validation
                    emails.append(email)
    except Exception as e:
        print(f"Error reading CSV file: {e}")
        return []
    
    if not emails:
        print("No valid emails found in the CSV file.")
        return []
    
    total_emails = len(emails)
    print(f"Found {total_emails} valid emails")
    
    # Check if we have more terminals than emails
    if num_terminals > total_emails:
        print(f"Warning: More terminals ({num_terminals}) than emails ({total_emails})")
        print(f"Adjusting to use {total_emails} terminals")
        num_terminals = total_emails
    
    # Calculate base emails per terminal and remainder
    base_emails_per_terminal = total_emails // num_terminals
    remainder = total_emails % num_terminals
    
    print(f"Dividing {total_emails} emails into {num_terminals} terminals")
    print(f"Base emails per terminal: {base_emails_per_terminal}")
    print(f"Remainder (to be distributed): {remainder}")
    
    # Divide emails into chunks
    chunk_files = []
    start_idx = 0
    
    for i in range(num_terminals):
        # Calculate how many emails go in this terminal
        # Distribute the remainder one by one to the first 'remainder' terminals
        emails_in_this_terminal = base_emails_per_terminal
        if i < remainder:
            emails_in_this_terminal += 1
        
        end_idx = start_idx + emails_in_this_terminal
        
        # Get emails for this terminal
        chunk_emails = emails[start_idx:end_idx]
        chunk_file = os.path.join(files_dir, f"T{i+1}email.csv")
        
        # Write chunk to CSV file
        with open(chunk_file, 'w', encoding='utf-8', newline='') as f:
            for email in chunk_emails:
                f.write(f"{email}\n")
        
        chunk_files.append(chunk_file)
        print(f"Terminal {i+1}: Created {chunk_file} with {len(chunk_emails)} emails (indices {start_idx+1}-{end_idx})")
        
        # Update start index for next chunk
        start_idx = end_idx
    
    # Verify that all emails were distributed
    total_distributed = sum(len(open(f, 'r').readlines()) for f in chunk_files)
    print(f"Total emails distributed: {total_distributed} of {total_emails}")
    
    if total_distributed != total_emails:
        print("WARNING: Not all emails were distributed. Please check your CSV file.")
    
    return chunk_files

def run_terminal(terminal_id: int, csv_path: str, output_queue: List, run_in_background: bool = False, max_retries: int = 3, job_id: str = None) -> None:
    """
    Run main.py in a cmd terminal with automated input.
    
    Args:
        terminal_id: ID of the terminal
        csv_path: Path to the CSV file containing emails for this terminal
        output_queue: Queue to store terminal output
        run_in_background: Whether to run the terminal in the background
        max_retries: Maximum number of retries if terminal fails to start
        job_id: Optional job ID for batch verification
    """
    try:
        # Get absolute path to CSV file
        abs_csv_path = os.path.abspath(csv_path)
        
        # Create files directory if it doesn't exist
        files_dir = os.path.join("terminal", "files")
        create_directory(files_dir)
        
        # Generate current date for verification name
        current_date = datetime.datetime.now().strftime("%Y%m%d")
        
        # Create output file for capturing terminal output
        output_file = os.path.join(files_dir, f"terminal_output_{terminal_id}.txt")
        
        # Create a batch file to run the command with input redirection
        batch_file = os.path.join(files_dir, f"terminal_cmd_{terminal_id}.bat")
        with open(batch_file, 'w') as f:
            f.write('@echo off\n')
            f.write(f'title Email Verifier Terminal {terminal_id}\n')
            f.write(f'cd /d "{os.getcwd()}"\n')
            f.write(f'echo Terminal {terminal_id} starting... > "{output_file}"\n')
            # Redirect stdout and stderr to the output file
            cmd_args = f'python main.py < "{files_dir}\\terminal_input_{terminal_id}.txt"'
            if job_id:
                cmd_args += f' --job-id "{job_id}"'
            f.write(f'{cmd_args} >> "{output_file}" 2>&1\n')
            f.write(f'echo Terminal {terminal_id} completed. >> "{output_file}"\n')
            f.write(f'echo Completed > "{files_dir}\\T{terminal_id}_completed.txt"\n')
            if not run_in_background:
                f.write('pause\n')
            else:
                f.write('exit\n')
        
        # Create input file with automated responses
        input_file = os.path.join(files_dir, f"terminal_input_{terminal_id}.txt")
        
        # Use a retry mechanism with file locks to avoid file access issues
        for attempt in range(max_retries):
            try:
                with open(input_file, 'w') as f:
                    f.write('2\n')  # Option 2: Verify multiple emails
                    f.write('1\n')  # Option 1: Load from CSV file
                    f.write(f'{abs_csv_path}\n')  # CSV path
                    f.write('y\n')  # Use multi-terminal: yes
                    f.write('8\n')  # Number of terminals: 2
                    f.write('n\n')  # Use real multiple terminals: no
                    f.write('n\n')  # Do you want to save these verification statistics? No
                    verification_name = f"TermiVerif{terminal_id}_{current_date}"
                    if job_id:
                        verification_name = f"{job_id}_T{terminal_id}"
                    f.write(f'{verification_name}\n')  # Verification name
                break
            except IOError as e:
                if attempt < max_retries - 1:
                    # Wait a random time before retrying to avoid conflicts
                    time.sleep(random.uniform(0.5, 2.0))
                else:
                    raise e
        
        # Start cmd process with the batch file
        if run_in_background:
            # Use /B flag to run the process in the background without a window
            process = subprocess.Popen(
                f'start /B cmd /c "{batch_file}"',
                shell=True
            )
        else:
            process = subprocess.Popen(
                ["start", "cmd", "/k", f"{batch_file}"],
                shell=True
            )
        
        # Add initial message to output queue
        output_queue.append((terminal_id, f"Terminal {terminal_id} started with CSV: {os.path.basename(csv_path)}"))
        
        # Start a thread to monitor the output file
        monitor_thread = threading.Thread(
            target=monitor_terminal_output,
            args=(terminal_id, output_file, output_queue)
        )
        monitor_thread.daemon = True
        monitor_thread.start()
        
    except Exception as e:
        print(f"Error in terminal {terminal_id}: {e}")
        output_queue.append((terminal_id, f"Error: {str(e)}"))

def monitor_terminal_output(terminal_id: int, output_file: str, output_queue: List) -> None:
    """
    Monitor the output file of a terminal and add new lines to the output queue.
    
    Args:
        terminal_id: ID of the terminal
        output_file: Path to the output file
        output_queue: Queue to store terminal output
    """
    # Wait for output file to be created
    while not os.path.exists(output_file):
        time.sleep(0.5)
    
    # Wait a bit to ensure file is ready for reading
    time.sleep(1)
    
    # Open the file and follow it
    last_position = 0
    while True:
        try:
            with open(output_file, 'r', encoding='utf-8', errors='ignore') as f:
                # Go to the last position we read
                f.seek(last_position)
                
                # Read new content
                new_content = f.read()
                if new_content:
                    # Process each line
                    for line in new_content.splitlines():
                        if line.strip():
                            output_queue.append((terminal_id, line.strip()))
                
                # Update last position
                last_position = f.tell()
            
            # Check if terminal has completed
            completion_marker = os.path.join(os.path.dirname(output_file), f"T{terminal_id}_completed.txt")
            if os.path.exists(completion_marker):
                output_queue.append((terminal_id, "Terminal completed processing"))
                break
            
            # Wait before checking again
            time.sleep(0.5)
            
        except Exception as e:
            # If there's an error reading the file, wait and try again
            time.sleep(1)

def check_completion(files_dir: str, num_terminals: int) -> bool:
    """
    Check if all terminals have completed.
    
    Args:
        files_dir: Directory containing terminal files
        num_terminals: Number of terminals
        
    Returns:
        bool: True if all terminals have completed, False otherwise
    """
    for i in range(1, num_terminals + 1):
        completion_marker = os.path.join(files_dir, f"T{i}_completed.txt")
        if not os.path.exists(completion_marker):
            return False
    return True

def display_progress(output_queue: List, files_dir: str, num_terminals: int) -> None:
    """
    Display progress from all terminals.
    
    Args:
        output_queue: Queue containing terminal output
        files_dir: Directory containing terminal files
        num_terminals: Number of terminals
    """
    last_display_time = time.time()
    displayed_lines = set()
    
    while not check_completion(files_dir, num_terminals):
        current_time = time.time()
        
        # Display new output every second
        if current_time - last_display_time >= 1:
            # Get all new lines from the queue
            new_lines = []
            for terminal_id, line in output_queue:
                line_key = f"{terminal_id}:{line}"
                if line_key not in displayed_lines:
                    new_lines.append((terminal_id, line))
                    displayed_lines.add(line_key)
            
            # Sort by terminal ID
            new_lines.sort(key=lambda x: x[0])
            
            # Display new lines
            for terminal_id, line in new_lines:
                print(f"Terminal {terminal_id}: {line}")
            
            last_display_time = current_time
        
        # Sleep to avoid high CPU usage
        time.sleep(0.1)
    
    print("All terminals have completed processing.")

def cleanup_terminal_files(files_dir: str) -> None:
    """
    Clean up terminal files after all terminals have completed.
    
    Args:
        files_dir: Directory containing terminal files
    """
    try:
        print("Cleaning up terminal files...")
        
        # Wait a bit to ensure all files are released
        time.sleep(5)
        
        # Delete all files in the terminal/files directory with retry mechanism
        for filename in os.listdir(files_dir):
            file_path = os.path.join(files_dir, filename)
            if os.path.isfile(file_path):
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        os.remove(file_path)
                        print(f"Deleted: {file_path}")
                        break
                    except Exception as e:
                        if attempt < max_retries - 1:
                            print(f"Retrying deletion of {file_path}...")
                            time.sleep(random.uniform(1, 3))  # Random delay before retry
                        else:
                            print(f"Could not delete {file_path}: {e}")
        
        print("Cleanup completed.")
    except Exception as e:
        print(f"Error during cleanup: {e}")

def main():
    """Main function to control multiple terminals."""
    print("Email Verification Terminal Controller")
    print("=====================================")
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Control multiple terminals for email verification")
    parser.add_argument("--num-terminals", type=int, help="Number of terminals to use")
    parser.add_argument("--csv-path", type=str, help="Path to CSV file containing emails")
    parser.add_argument("--background", action="store_true", help="Run terminals in background")
    parser.add_argument("--job-id", type=str, help="Job ID for batch verification")
    args = parser.parse_args()
    
    # Get number of terminals
    num_terminals = args.num_terminals
    if not num_terminals:
        try:
            num_terminals = int(input("How many terminals do you want to use? (1-32): "))
            num_terminals = min(max(1, num_terminals), 32) 
        except ValueError:
            print("Invalid input. Using 2 terminals.")
            num_terminals = 2
    
    # Get CSV file path
    csv_path = args.csv_path
    if not csv_path:
        csv_path = input("Enter the path to the CSV file: ")
    
    if not os.path.exists(csv_path):
        print(f"CSV file not found: {csv_path}")
        return
    
    # Get job ID
    job_id = args.job_id
    
    # Ask about background mode if not specified in args
    run_in_background = args.background
    if not args.background:
        background_choice = input("Run terminals in background (hidden)? (y/n): ").lower()
        run_in_background = background_choice == 'y'
    
    # Divide emails into chunks
    chunk_files = divide_emails(csv_path, num_terminals)
    if not chunk_files:
        return
    
    # Create shared output queue
    output_queue = []
    
    # Create terminal directory and files subdirectory
    terminal_dir = "terminal"
    files_dir = os.path.join(terminal_dir, "files")
    create_directory(terminal_dir)
    create_directory(files_dir)
    
    # If job_id is provided, create job directory in results
    if job_id:
        job_dir = os.path.join("./results", job_id)
        create_directory(job_dir)
    
    # Start terminal threads in pairs for better speed
    terminal_threads = []
    i = 0
    while i < len(chunk_files):
        # Start a pair of terminals (or just one if we're at the end)
        threads_to_start = min(2, len(chunk_files) - i)
        current_threads = []
        
        for j in range(threads_to_start):
            terminal_id = i + j + 1
            thread = threading.Thread(
                target=run_terminal, 
                args=(terminal_id, chunk_files[i+j], output_queue, run_in_background),
                kwargs={"job_id": job_id}
            )
            thread.daemon = True
            thread.start()
            current_threads.append(thread)
            terminal_threads.append(thread)
        
        # Add a small delay between starting pairs of terminals
        time.sleep(3)
        i += threads_to_start
    
    print(f"Started {len(terminal_threads)} terminals for email verification")
    print(f"Terminals running in {'background (hidden)' if run_in_background else 'visible'} mode")
    
    # Start display thread
    display_thread = threading.Thread(
        target=display_progress, 
        args=(output_queue, files_dir, len(chunk_files))
    )
    display_thread.daemon = True
    display_thread.start()
    
    # Wait for all terminal threads to complete
    for thread in terminal_threads:
        thread.join()
    
    # Wait for display thread to complete
    display_thread.join(timeout=60)
    
    print("All terminals have completed processing.")
    
    # Clean up terminal files
    cleanup_terminal_files(files_dir)
    

if __name__ == "__main__":
    main()

