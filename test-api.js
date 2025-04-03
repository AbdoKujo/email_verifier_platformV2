/**
 * Email Verifier API Tester
 * 
 * This file creates a simple HTML interface to test all API endpoints
 * for the Email Verifier application.
 */

// Create HTML structure when the page loads
document.addEventListener('DOMContentLoaded', function() {
    const container = document.createElement('div');
    container.className = 'container';
    document.body.appendChild(container);

    // Add title
    const title = document.createElement('h1');
    title.textContent = 'Email Verifier API Tester';
    container.appendChild(title);

    // API base URL
    const apiUrlInput = document.createElement('input');
    apiUrlInput.type = 'text';
    apiUrlInput.value = 'http://localhost:5000';
    apiUrlInput.id = 'api-url';
    apiUrlInput.placeholder = 'API Base URL';
    apiUrlInput.style.width = '300px';
    apiUrlInput.style.marginBottom = '20px';
    container.appendChild(apiUrlInput);

    // Create sections for different endpoint types
    const sections = [
        { id: 'verification', title: 'Verification Endpoints' },
        { id: 'results', title: 'Results Endpoints' },
        { id: 'statistics', title: 'Statistics Endpoints' },
        { id: 'settings', title: 'Settings Endpoints' }
    ];

    sections.forEach(section => {
        const sectionElem = createSection(section.title, section.id);
        container.appendChild(sectionElem);
    });

    // Add response display area
    const responseArea = document.createElement('div');
    responseArea.id = 'response';
    responseArea.className = 'response';
    container.appendChild(responseArea);

    // Add verification endpoints
    addEndpoint(
        'verification',
        'Verify a Single Email',
        'POST',
        '/api/verify/email',
        { email: 'example@example.com' },
        'verifyEmail'
    );

    addEndpoint(
        'verification',
        'Verify Batch of Emails',
        'POST',
        '/api/verify/batch',
        { 
            emails: [
                'info@xos.ma', 
                'phar.s@yahoo.com', 
                'pharmacie.casablanca10@gmail.com'
            ], 
            job_id: 'my_job_123' 
        },
        'verifyBatch'
    );

    addEndpoint(
        'verification',
        'Verify Batch of Emails (Streaming)',
        'POST',
        '/api/verify/batch',
        { 
            emails: [
                'info@xos.ma', 
                'phar.s@yahoo.com', 
                'pharmacie.casablanca10@gmail.com'
            ], 
            job_id: 'my_job_123' 
        },
        'verifyBatchStream'
    );

    addEndpoint(
        'verification',
        'Get Job Status',
        'GET',
        '/api/verify/status/my_job_123',
        null,
        'jobStatus'
    );

    // Add results endpoints
    addEndpoint(
        'results',
        'Get All Results',
        'GET',
        '/api/results',
        null,
        'allResults'
    );

    addEndpoint(
        'results',
        'Get Job Results',
        'GET',
        '/api/results/my_job_123',
        null,
        'jobResults'
    );

    // Add statistics endpoints
    addEndpoint(
        'statistics',
        'Get Global Statistics',
        'GET',
        '/api/statistics',
        null,
        'globalStats'
    );

    addEndpoint(
        'statistics',
        'Get Email History',
        'GET',
        '/api/statistics/history/email?email=example@example.com',
        null,
        'emailHistory'
    );

    addEndpoint(
        'statistics',
        'Get Category History',
        'GET',
        '/api/statistics/history?category=valid',
        null,
        'categoryHistory'
    );

    // Add settings endpoints
    addEndpoint(
        'settings',
        'Get All Settings',
        'GET',
        '/api/settings',
        null,
        'allSettings'
    );

    addEndpoint(
        'settings',
        'Update Settings',
        'PUT',
        '/api/settings',
        {
            multi_terminal_enabled: {value: 'True', enabled: true},
            terminal_count: {value: '4', enabled: true}
        },
        'updateSettings'
    );

    // Add some basic styling
    addStyles();
});

/**
 * Creates a section in the UI
 */
function createSection(title, id) {
    const section = document.createElement('div');
    section.className = 'section';
    section.id = id + '-section';
    
    const sectionTitle = document.createElement('h2');
    sectionTitle.textContent = title;
    section.appendChild(sectionTitle);
    
    return section;
}

/**
 * Adds an endpoint test UI
 */
function addEndpoint(sectionId, title, method, path, body, id) {
    const section = document.getElementById(sectionId + '-section');
    
    const endpointDiv = document.createElement('div');
    endpointDiv.className = 'endpoint';
    
    // Create endpoint title
    const endpointTitle = document.createElement('h3');
    endpointTitle.textContent = title;
    endpointDiv.appendChild(endpointTitle);
    
    // Create endpoint details
    const details = document.createElement('div');
    details.className = 'details';
    details.innerHTML = `<strong>${method}</strong>: <code>${path}</code>`;
    endpointDiv.appendChild(details);
    
    // Create input for editable path or body
    if (body || path.includes('?') || path.includes(':')) {
        const inputLabel = document.createElement('div');
        inputLabel.textContent = body ? 'Request Body:' : 'Path/Query Parameters:';
        endpointDiv.appendChild(inputLabel);
        
        const input = document.createElement('textarea');
        input.id = id + '-input';
        input.rows = 4;
        input.style.width = '100%';
        
        if (body) {
            input.value = JSON.stringify(body, null, 2);
        } else {
            input.value = path;
        }
        
        endpointDiv.appendChild(input);
    }
    
    // Create test button
    const button = document.createElement('button');
    button.textContent = 'Test Endpoint';
    button.id = id + '-button';
    button.addEventListener('click', () => {
        const apiUrl = document.getElementById('api-url').value;
        let url = apiUrl;
        
        if (body) {
            // If we have a body, use the original path
            url += path;
        } else if (document.getElementById(id + '-input')) {
            // If we have an editable path but no body
            url += document.getElementById(id + '-input').value;
        } else {
            // Otherwise just use the original path
            url += path;
        }
        
        const options = {
            method: method,
            headers: {}
        };
        
        if (body) {
            options.headers['Content-Type'] = 'application/json';
            try {
                options.body = document.getElementById(id + '-input').value;
                // Check if valid JSON
                JSON.parse(options.body);
            } catch (e) {
                showResponse({ error: 'Invalid JSON in request body' });
                return;
            }
        }
        
        // Show loading state
        showResponse({ status: 'Loading...' });
        
        // Special handling for streaming batch verification
        if (id === 'verifyBatchStream') {
            handleStreamingResponse(url, options);
        } else {
            // Regular non-streaming endpoint
            fetch(url, options)
                .then(response => {
                    const contentType = response.headers.get("content-type");
                    if (contentType && contentType.indexOf("application/json") !== -1) {
                        return response.json().then(data => {
                            return {
                                status: response.status,
                                statusText: response.statusText,
                                data: data
                            };
                        });
                    } else {
                        return response.text().then(text => {
                            return {
                                status: response.status,
                                statusText: response.statusText,
                                data: text
                            };
                        });
                    }
                })
                .then(response => {
                    showResponse(response);
                })
                .catch(error => {
                    showResponse({ error: error.message });
                });
        }
    });
    
    endpointDiv.appendChild(button);
    section.appendChild(endpointDiv);
}

/**
 * Handle streaming response for batch verification
 */
function handleStreamingResponse(url, options) {
    const responseArea = document.getElementById('response');
    
    // Clear previous response
    responseArea.innerHTML = '';
    
    // Create response header
    const header = document.createElement('h3');
    header.textContent = 'Streaming Response';
    responseArea.appendChild(header);
    
    // Create container for stream items
    const streamContainer = document.createElement('div');
    streamContainer.className = 'stream-container';
    responseArea.appendChild(streamContainer);
    
    // Status display
    const status = document.createElement('div');
    status.className = 'status';
    status.textContent = 'Status: Connecting...';
    responseArea.insertBefore(status, streamContainer);
    
    fetch(url, options)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            
            status.textContent = `Status: ${response.status} ${response.statusText} - Stream connected`;
            
            // Get a reader to read the stream
            const reader = response.body.getReader();
            
            // Create a decoder for UTF-8 text
            const decoder = new TextDecoder();
            
            // Buffer for incomplete chunks
            let buffer = '';
            
            // Function to process the stream
            function processStream() {
                return reader.read().then(({ done, value }) => {
                    // If the stream is done, return
                    if (done) {
                        status.textContent += ' - Stream completed';
                        return;
                    }
                    
                    // Decode the chunk and add to buffer
                    const chunk = decoder.decode(value, { stream: true });
                    buffer += chunk;
                    
                    // Process complete lines in the buffer
                    const lines = buffer.split('\n');
                    buffer = lines.pop(); // Keep the last (potentially incomplete) line in the buffer
                    
                    // Process each complete line
                    for (const line of lines) {
                        if (line.trim() === '') continue;
                        
                        try {
                            const json = JSON.parse(line);
                            addStreamItem(json);
                        } catch (e) {
                            console.error('Error parsing JSON:', e, line);
                            addStreamItem({ error: `Invalid JSON: ${line}` });
                        }
                    }
                    
                    // Continue reading the stream
                    return processStream();
                }).catch(error => {
                    status.textContent = `Error: ${error.message}`;
                });
            }
            
            // Start processing the stream
            return processStream();
        })
        .catch(error => {
            status.textContent = `Error: ${error.message}`;
        });
}

/**
 * Add a new item to the stream container
 */
function addStreamItem(json) {
    const streamContainer = document.querySelector('.stream-container');
    
    const item = document.createElement('div');
    item.className = 'stream-item';
    
    // Add appropriate styling based on the type of message
    if (json.status === 'started') {
        item.classList.add('stream-start');
    } else if (json.status === 'completed') {
        item.classList.add('stream-end');
    } else if (json.email) {
        item.classList.add(json.status || 'stream-result');
    }
    
    // Create pretty display
    const pre = document.createElement('pre');
    pre.textContent = JSON.stringify(json, null, 2);
    item.appendChild(pre);
    
    streamContainer.appendChild(item);
    
    // Scroll to the bottom to show latest results
    streamContainer.scrollTop = streamContainer.scrollHeight;
}

/**
 * Shows response in the response area
 */
function showResponse(response) {
    const responseArea = document.getElementById('response');
    
    // Clear previous response
    responseArea.innerHTML = '';
    
    // Create response header
    const header = document.createElement('h3');
    header.textContent = 'Response';
    responseArea.appendChild(header);
    
    // Show status if available
    if (response.status) {
        const status = document.createElement('div');
        status.className = 'status';
        status.textContent = `Status: ${response.status} ${response.statusText || ''}`;
        responseArea.appendChild(status);
    }
    
    // Show error if available
    if (response.error) {
        const error = document.createElement('div');
        error.className = 'error';
        error.textContent = `Error: ${response.error}`;
        responseArea.appendChild(error);
        return;
    }
    
    // Create pretty response JSON
    const pre = document.createElement('pre');
    let responseText;
    
    if (typeof response.data === 'object') {
        responseText = JSON.stringify(response.data, null, 2);
    } else {
        responseText = response.data || JSON.stringify(response, null, 2);
    }
    
    pre.textContent = responseText;
    responseArea.appendChild(pre);
    
    // Scroll to response
    responseArea.scrollIntoView({ behavior: 'smooth' });
}

/**
 * Add basic styles to the page
 */
function addStyles() {
    const style = document.createElement('style');
    style.textContent = `
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }
        
        .container {
            max-width: 1000px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 5px;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
        }
        
        h1 {
            color: #333;
            border-bottom: 1px solid #eee;
            padding-bottom: 10px;
        }
        
        h2 {
            color: #444;
            margin-top: 30px;
        }
        
        .section {
            margin-bottom: 30px;
        }
        
        .endpoint {
            background-color: #f9f9f9;
            padding: 15px;
            margin-bottom: 15px;
            border-radius: 3px;
            border-left: 4px solid #2196F3;
        }
        
        .details {
            margin: 10px 0;
        }
        
        button {
            background-color: #2196F3;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 3px;
            cursor: pointer;
            margin-top: 10px;
        }
        
        button:hover {
            background-color: #0b7dda;
        }
        
        textarea {
            font-family: monospace;
            margin: 10px 0;
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 3px;
        }
        
        .response {
            margin-top: 40px;
            padding: 15px;
            background-color: #f0f0f0;
            border-radius: 3px;
        }
        
        pre {
            background-color: #eee;
            padding: 15px;
            overflow-x: auto;
            border-radius: 3px;
            margin: 0;
        }
        
        code {
            font-family: monospace;
            background-color: #eee;
            padding: 2px 5px;
            border-radius: 3px;
        }
        
        .status {
            margin-bottom: 10px;
            font-weight: bold;
        }
        
        .error {
            color: #d32f2f;
            margin-bottom: 10px;
            font-weight: bold;
        }
        
        /* Stream specific styles */
        .stream-container {
            max-height: 500px;
            overflow-y: auto;
            border: 1px solid #ddd;
            border-radius: 3px;
        }
        
        .stream-item {
            border-bottom: 1px solid #ddd;
            padding: 5px;
            margin: 0;
        }
        
        .stream-item:nth-child(even) {
            background-color: #f5f5f5;
        }
        
        .stream-start {
            background-color: #e8f5e9 !important;
            border-left: 4px solid #4caf50;
        }
        
        .stream-end {
            background-color: #e1f5fe !important;
            border-left: 4px solid #03a9f4;
        }
        
        .valid {
            background-color: #e8f5e9 !important;
            border-left: 4px solid #4caf50;
        }
        
        .invalid {
            background-color: #ffebee !important;
            border-left: 4px solid #f44336;
        }
        
        .risky {
            background-color: #fff8e1 !important;
            border-left: 4px solid #ffc107;
        }
    `;
    document.head.appendChild(style);
}