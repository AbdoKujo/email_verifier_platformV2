import fetch from 'node-fetch';

// API endpoints utility functions
const API_BASE_URL = 'http://localhost:5000'; 

// 1. GET:/api/statistics/category
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

// 2. GET:/api/verify/status/{job_id}
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

// 3. POST:/api/verify/batch
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
    
    // Handle streaming response for Node.js
    let result = '';
    response.body.on('data', (chunk) => {
      const chunkStr = chunk.toString();
      result += chunkStr;
      console.log('Received batch verification chunk:', chunkStr);
    });
    
    return new Promise((resolve, reject) => {
      response.body.on('end', () => {
        console.log('Batch verification complete:', result);
        resolve(result);
      });
      
      response.body.on('error', (err) => {
        reject(err);
      });
    });
  } catch (error) {
    console.error('Failed to verify batch:', error);
    throw error;
  }
}

// 4. GET:/api/batches
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

// 5. PUT:/api/batches/{batch_id}/name
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

// Run the functions to test
async function runTests() {
  try {
    // Get category statistics
    console.log("\n=== Test 1: Get Category Statistics ===");
    await getCategoryStatistics();
    
    // Get batch names - we'll use the first batch ID for other tests
    console.log("\n=== Test 2: Get All Batch Names ===");
    const batchesResponse = await getAllBatchNames();
    let firstBatchId = null;
    if (batchesResponse && batchesResponse.batches) {
      const batchIds = Object.keys(batchesResponse.batches);
      if (batchIds.length > 0) {
        firstBatchId = batchIds[0];
      }
    }
    
    // Check verification status if we have a batch ID
    if (firstBatchId) {
      console.log(`\n=== Test 3: Get Verification Status for ${firstBatchId} ===`);
      await getVerificationStatus(firstBatchId);
      
      // Update batch name
      console.log(`\n=== Test 4: Update Batch Name for ${firstBatchId} ===`);
      await updateBatchName(firstBatchId, "Updated via Node.js " + new Date().toISOString());
    } else {
      console.log("No batch IDs found, skipping tests that require a batch ID");
    }
    
    // Verify a batch of emails
    console.log("\n=== Test 5: Verify Batch of Emails ===");
    const emailsToVerify = [
      'test1@example.com',
      'test2@example.com',
      'invalid@nonexistentdomain.xyz'
    ];
    await verifyBatch(emailsToVerify);
    
  } catch (error) {
    console.error("Test run failed:", error);
  }
}

// Run all tests
runTests();

/*
Sample test results:

=== Test 1: Get Category Statistics ===
Category Statistics: {
  categories: { invalid: 230, risky: 78, total: 437, valid: 129 },
  timestamp: '2025-04-16 22:51:00'
}

=== Test 2: Get All Batch Names ===
All batch names: {
  batches: {
    batch_1743908523_2ac47056: 'naaaaaame',
    batch_1743964425_8b3315ad: 'testing1',
    batch_1743966262_2d296958: 'testing13',
    batch_1743966424_3a6f8f96: 'testing13',
    batch_1743973332_68d480f5: 'testing2',
    batch_1743974050_a2c02c93: 'testing3',
    batch_1744397578_6cbcb34a: 'testing4',
    batch_1744397891_bd2b9bfb: 'testing5',
    batch_1744398209_da11b31a: 'testing6',
    batch_1744400663_e82f755a: 'testing7',
    batch_1744667208_af3089c8: 'testing8',
    batch_1744667311_525d689f: 'testing9',
    batch_1744667408_2348b712: 'testing10',
    batch_1744670760_8c487251: 'testing11',
    batch_1744674347_40ad3586: 'testing12'
  }
}

=== Test 3: Get Verification Status for batch_1743908523_2ac47056 ===        
Verification status for job batch_1743908523_2ac47056: {
  email_results: {
    'i.ghcxvcxomri@aui.ma': {
      category: 'invalid',
      email: 'i.ghcxvcxomri@aui.ma',
      provider: 'microsoft'
    },
    'incxvfsdo@enzazaden.com.br': {
      category: 'invalid',
      email: 'incxvfsdo@enzazaden.com.br',
      provider: 'microsoft'
    },
    'joisdnxcvcus@experiencemorocco.com': {
      category: 'invalid',
      email: 'joisdnxcvcus@experiencemorocco.com',
      provider: 'google'
    }
  },
  end_time: '2025-04-06 04:02:19',
  job_id: 'batch_1743908523_2ac47056',
  results: { custom: 0, invalid: 3, risky: 0, valid: 0 },
  start_time: '2025-04-06 04:02:03',
  status: 'completed',
  total_emails: 3,
  verified_emails: 3
}

=== Test 4: Update Batch Name for batch_1743908523_2ac47056 ===
Batch batch_1743908523_2ac47056 name updated: {
  message: 'Batch name updated to "Updated via Node.js 2025-04-16T21:51:00.723Z"',
  success: true
}

=== Test 5: Verify Batch of Emails ===
Received batch verification chunk: {"job_id": "batch_1744840260_125df2cf", "status": "started", "total_emails": 3, "message": "Batch verification started", "timestamp": "2025-04-16 22:51:00"}

Received batch verification chunk: {"email": "test1@example.com", "category": "invalid", "provider": "example.com", "timestamp": "2025-04-16 22:51:02"}   

Received batch verification chunk: {"email": "test2@example.com", "category": "invalid", "provider": "example.com", "timestamp": "2025-04-16 22:51:02"}   

Received batch verification chunk: {"email": "invalid@nonexistentdomain.xyz", "category": "risky", "provider": "nonexistentdomain.xyz", "timestamp": "2025-04-16 22:51:07"}

Received batch verification chunk: {"job_id": "batch_1744840260_125df2cf", "status": "completed", "total_emails": 3, "verified_emails": 3, "results": {"valid": 0, "invalid": 2, "risky": 1, "custom": 0}, "timestamp": "2025-04-16 22:51:07"}

Batch verification complete: {"job_id": "batch_1744840260_125df2cf", "status": "started", "total_emails": 3, "message": "Batch verification started", "timestamp": "2025-04-16 22:51:00"}
{"email": "test1@example.com", "category": "invalid", "provider": "example.com", "timestamp": "2025-04-16 22:51:02"}
{"email": "test2@example.com", "category": "invalid", "provider": "example.com", "timestamp": "2025-04-16 22:51:02"}
{"email": "invalid@nonexistentdomain.xyz", "category": "risky", "provider": "nonexistentdomain.xyz", "timestamp": "2025-04-16 22:51:07"}
{"job_id": "batch_1744840260_125df2cf", "status": "completed", "total_emails": 3, "verified_emails": 3, "results": {"valid": 0, "invalid": 2, "risky": 1, "custom": 0}, "timestamp": "2025-04-16 22:51:07"}
*/

