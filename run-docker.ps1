# PowerShell script to run the Email Verification Docker container
param (
    [string]$Command = "main.py",
    [switch]$Interactive = $false,
    [switch]$Build = $false,
    [switch]$UseLocalFiles = $false,
    [switch]$Api = $false
)

# Project directory (current directory)
$ProjectDir = Get-Location

# Create required directories if they don't exist
$Directories = @("data", "screenshots", "results", "terminal", "terminal\files")
foreach ($Dir in $Directories) {
    if (-not (Test-Path "$ProjectDir\$Dir")) {
        New-Item -Path "$ProjectDir\$Dir" -ItemType Directory -Force
        Write-Host "Created directory: $Dir"
    }
}

# Build the Docker image if requested
if ($Build) {
    Write-Host "Building Docker image..."
    docker build -t email-verifier .
}

# List of scripts that require interactive mode
$InteractiveScripts = @("main.py", "terminalController.py")

# Determine if we should run in interactive mode
# Auto-enable interactive mode for certain scripts unless API mode is requested
$ShouldBeInteractive = $Interactive -or (($InteractiveScripts -contains $Command) -and -not $Api)
$InteractiveFlag = ""

if ($ShouldBeInteractive) {
    $InteractiveFlag = "-it"
    Write-Host "Running in interactive mode"
}

# Adjust command if API mode is requested
if ($Api) {
    $Command = "api/app.py"
    Write-Host "Running in API mode"
}

# Run the Docker container with the specified command
Write-Host "Running: $Command"
$DockerCmd = "docker run $InteractiveFlag --rm "

# Only mount directories for data exchange, not code
$DockerCmd += "-v `"${ProjectDir}\data:/app/data`" " +
             "-v `"${ProjectDir}\screenshots:/app/screenshots`" " +
             "-v `"${ProjectDir}\results:/app/results`" " +
             "-v `"${ProjectDir}\terminal:/app/terminal`" " +
             "-p 5000:5000 "

# Mount local code directory only if explicitly requested
if ($UseLocalFiles) {
    $DockerCmd += "-v `"${ProjectDir}:/app`" "
}

$DockerCmd += "email-verifier $Command"

Write-Host "Executing: $DockerCmd"
Invoke-Expression $DockerCmd