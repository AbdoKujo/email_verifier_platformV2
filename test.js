// API endpoints utility functions
const API_BASE_URL = 'http://localhost:5000'; // Change this to your API URL

// 1. GET:/api/statistics/category - Get statistics by category
async function getCategoryStatistics() {
  try {
    const response = await fetch(`${API_BASE_URL}/api/statistics/category`, {
      method: 'GET',
      headers: {
        'Accept': 'application/json'
      }
    });
    
    if (!response.ok) {
      throw new Error(`HTTP error ${response.status}`);
    }
    
    const data = await response.json();
    console.log('Category Statistics:', data);
    return data;
  } catch (error) {
    console.error('Failed to get category statistics:', error);
    throw error;
  }
}

// 2. GET:/api/verify/status/{job_id} - Check verification job status
async function getVerificationStatus(jobId) {
  try {
    if (!jobId) {
      throw new Error('Job ID is required');
    }
    
    const response = await fetch(`${API_BASE_URL}/api/verify/status/${jobId}`, {
      method: 'GET',
      headers: {
        'Accept': 'application/json'
      }
    });
    
    if (!response.ok) {
      throw new Error(`HTTP error ${response.status}`);
    }
    
    const data = await response.json();
    console.log(`Verification status for job ${jobId}:`, data);
    return data;
  } catch (error) {
    console.error('Failed to get verification status:', error);
    throw error;
  }
}

// 3. POST:/api/verify/batch - Submit emails for batch verification
async function verifyBatch(emails) {
  try {
    if (!emails || !Array.isArray(emails) || emails.length === 0) {
      throw new Error('Valid email array is required');
    }
    
    const response = await fetch(`${API_BASE_URL}/api/verify/batch`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      body: JSON.stringify({ emails: emails })
    });
    
    if (!response.ok) {
      throw new Error(`HTTP error ${response.status}`);
    }
    
    // This endpoint returns streaming results
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let result = '';
    
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      
      const chunk = decoder.decode(value, { stream: true });
      result += chunk;
      console.log('Received batch verification chunk:', chunk);
    }
    
    console.log('Batch verification complete:', result);
    return result;
  } catch (error) {
    console.error('Failed to verify batch:', error);
    throw error;
  }
}

// 4. GET:/api/batches - Get all batch IDs and names
async function getAllBatchNames() {
  try {
    const response = await fetch(`${API_BASE_URL}/api/batches`, {
      method: 'GET',
      headers: {
        'Accept': 'application/json'
      }
    });
    
    if (!response.ok) {
      throw new Error(`HTTP error ${response.status}`);
    }
    
    const data = await response.json();
    console.log('All batch names:', data);
    return data;
  } catch (error) {
    console.error('Failed to get batch names:', error);
    throw error;
  }
}

// 5. PUT:/api/batches/{batch_id}/name - Update batch name
async function updateBatchName(batchId, newName) {
  try {
    if (!batchId) {
      throw new Error('Batch ID is required');
    }
    
    if (!newName) {
      throw new Error('New batch name is required');
    }
    
    const response = await fetch(`${API_BASE_URL}/api/batches/${batchId}/name`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      body: JSON.stringify({ name: newName })
    });
    
    if (!response.ok) {
      throw new Error(`HTTP error ${response.status}`);
    }
    
    const data = await response.json();
    console.log(`Batch ${batchId} name updated:`, data);
    return data;
  } catch (error) {
    console.error('Failed to update batch name:', error);
    throw error;
  }
}

// Usage examples:
/*
// Example 1: Get category statistics
getCategoryStatistics()
  .then(data => console.log('Success:', data))
  .catch(error => console.error('Error:', error));

// Example 2: Check verification status
getVerificationStatus('batch_1743908523_2ac47056')
  .then(data => console.log('Success:', data))
  .catch(error => console.error('Error:', error));

// Example 3: Verify batch of emails
const emailsToVerify = [
  'example1@example.com',
  'example2@example.com',
  'example3@example.com'
];
verifyBatch(emailsToVerify)
  .then(data => console.log('Success:', data))
  .catch(error => console.error('Error:', error));

// Example 4: Get all batch names
getAllBatchNames()
  .then(data => console.log('Success:', data))
  .catch(error => console.error('Error:', error));

// Example 5: Update batch name
updateBatchName('batch_1743908523_2ac47056', 'New Batch Name')
  .then(data => console.log('Success:', data))
  .catch(error => console.error('Error:', error));
*/