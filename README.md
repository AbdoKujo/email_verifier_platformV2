# Email Verification Tool

A Docker-based tool for verifying email addresses and managing email campaigns.

## Overview

This tool provides functionality to verify email addresses through various methods including SMTP validation, MX record checks, and bounce verification. It runs in a Docker container, ensuring consistent behavior across different environments.

## Features

- Single and batch email verification
- Multiple verification methods (SMTP, MX, API, Selenium)
- Bounce verification for improved accuracy
- Multi-terminal processing for faster verification
- Comprehensive API for integration with other systems
- Results management and statistics tracking
- Configurable settings for verification behavior

## Directory Structure

- `data/` - Input/output data files for email verification
- `screenshots/` - Screenshots captured during verification processes
- `results/` - Results of verification operations
- `terminal/` - Terminal output and command files
  - `terminal/files/` - Files used by the terminal controller

## Getting Started

### Prerequisites

- Docker installed on your system
- PowerShell (for Windows users) or Bash (for Linux/Mac users)

### Installation

1. Clone the repository
2. Build the Docker image:
   ```powershell
   .\run-docker.ps1 -Build
   ```
   
   Or build directly with Docker:
   ```bash
   docker build -t email-verifier .
   ```

## Usage

### Direct Docker Command

Run the API service with all necessary volume mounts:

```bash
# Windows
docker run -p 5000:5000 -v "$(pwd)\data:/app/data" -v "$(pwd)\results:/app/results" -v "$(pwd)\screenshots:/app/screenshots" -v "$(pwd)\terminal:/app/terminal" email-verifier api/app.py

# Linux/Mac
docker run -p 5000:5000 -v "$(pwd)/data:/app/data" -v "$(pwd)/results:/app/results" -v "$(pwd)/screenshots:/app/screenshots" -v "$(pwd)/terminal:/app/terminal" email-verifier api/app.py
```

### Basic Usage

Run the default script:
```powershell
.\run-docker.ps1
```

### Running Specific Scripts

```powershell
.\run-docker.ps1 -Command "script_name.py"
```

### Interactive Mode

Some scripts (like main.py and terminalController.py) run in interactive mode by default:
```powershell
.\run-docker.ps1 -Interactive
```

### API Mode

Run the tool as an API service:
```powershell
.\run-docker.ps1 -Api
```

This starts the API on port 5000 (accessible at http://localhost:5000).

### Development Mode

For development, you can mount local files into the container:
```powershell
.\run-docker.ps1 -UseLocalFiles
```

## Parameters

The run-docker.ps1 script accepts the following parameters:

- `-Command` - Specifies which Python script to run (default: main.py)
- `-Interactive` - Forces interactive mode
- `-Build` - Builds the Docker image before running
- `-UseLocalFiles` - Mounts local files into the container for development
- `-Api` - Runs in API mode (uses api/app.py)

## Examples

Run the main script interactively:
```powershell
.\run-docker.ps1
```

Run in API mode:
```powershell
.\run-docker.ps1 -Api
```

Run API mode with direct Docker command:
```bash
docker run -p 5000:5000 -v "$(pwd)\data:/app/data" -v "$(pwd)\results:/app/results" -v "$(pwd)\screenshots:/app/screenshots" -v "$(pwd)\terminal:/app/terminal" email-verifier api/app.py
```

Build the image and run a specific script:
```powershell
.\run-docker.ps1 -Build -Command "custom_script.py"
```

## API Endpoints

When running in API mode, the service provides various endpoints:

- `GET /` - Web-based API tester interface
- `POST /api/verify/email` - Verify a single email address
- `POST /api/verify/batch` - Verify a batch of email addresses
- `GET /api/verify/status/{job_id}` - Check verification job status
- `GET /api/results` - Get all verification results
- `GET /api/results/{job_id}` - Get results for a specific job
- `GET /api/results/batches` - Get all batch IDs
- `GET /api/batches` - Get all batch names
- `PUT /api/batches/{batch_id}/name` - Update batch name
- `GET /api/statistics` - Get global statistics
- `GET /api/statistics/category` - Get statistics by category

Visit http://localhost:5000 for a full API tester interface.
