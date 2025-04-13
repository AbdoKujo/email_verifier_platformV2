from flask import Flask, request, jsonify, Response, stream_with_context, send_from_directory
from flask_cors import CORS
import os
import sys
import json
import uuid
import time
from datetime import datetime

# Add parent directory to path to import models
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import API services
from api.verification_service import VerificationService
from api.results_service import ResultsService
from api.statistics_service import StatisticsService
from api.settings_service import SettingsService
# Import BounceService
from api.bounce_service import BounceService

# Create Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Initialize services
verification_service = VerificationService()
results_service = ResultsService()
statistics_service = StatisticsService()
settings_service = SettingsService()
# Initialize BounceService
bounce_service = BounceService()

# Serve HTML Tester
@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

# API Routes

# Verification endpoints
@app.route('/api/verify/email', methods=['POST'])
def verify_email():
    """Verify a single email address."""
    data = request.get_json()
    
    if not data or 'email' not in data:
        return jsonify({'error': 'Email is required'}), 400
    
    email = data['email']
    result = verification_service.verify_single_email(email)
    
    return jsonify(result)

@app.route('/api/verify/batch', methods=['POST'])
def verify_batch():
    """
    Verify a batch of email addresses.
    This endpoint streams results as they become available.
    """
    data = request.get_json()
    
    if not data or 'emails' not in data:
        return jsonify({'error': 'Emails list is required'}), 400
    
    emails = data['emails']
    job_id = data.get('job_id', f"batch_{int(time.time())}_{uuid.uuid4().hex[:8]}")
    
    # Use streaming response to provide real-time updates
    def generate():
        for result in verification_service.verify_batch_emails_stream(emails, job_id):
            yield json.dumps(result) + '\n'
    
    # Return a streaming response
    return Response(stream_with_context(generate()), 
                   mimetype='application/json',
                   headers={'X-Accel-Buffering': 'no'})

@app.route('/api/verify/status/<job_id>', methods=['GET'])
def verify_status(job_id):
    """Get verification job status."""
    status = verification_service.get_job_status(job_id)
    
    if status:
        return jsonify(status)
    else:
        return jsonify({'error': 'Job not found'}), 404

# Bounce verification endpoints
@app.route('/api/verify/bounce', methods=['POST'])
def verify_bounce():
    """Verify emails using the bounce method."""
    data = request.get_json()
    
    if not data or 'emails' not in data:
        return jsonify({'error': 'Emails list is required'}), 400
    
    emails = data['emails']
    existing_batch_id = data.get('batch_id')
    
    result = bounce_service.initiate_bounce_verification(emails, existing_batch_id)
    
    return jsonify(result)

@app.route('/api/verify/bounce/status/<batch_id>', methods=['GET'])
def bounce_status(batch_id):
    """Get bounce verification status."""
    status = bounce_service.check_bounce_verification(batch_id)
    
    return jsonify(status)

@app.route('/api/verify/bounce/process/<batch_id>', methods=['POST'])
def process_bounce(batch_id):
    """Process bounce responses for a verification batch."""
    result = bounce_service.process_bounce_responses(batch_id)
    
    return jsonify(result)

# Results endpoints
@app.route('/api/results', methods=['GET'])
def get_all_results():
    """Get all verification results."""
    results = results_service.get_all_results()
    return jsonify(results)

@app.route('/api/results/<job_id>', methods=['GET'])
def get_job_results(job_id):
    """Get verification results for a specific job."""
    results = results_service.get_job_results(job_id)
    
    if results:
        return jsonify(results)
    else:
        return jsonify({'error': 'Job not found'}), 404

@app.route('/api/results/bounce', methods=['GET'])
def get_bounce_results():
    """Get all bounce verification results."""
    results = results_service.get_bounce_results()
    
    return jsonify(results)

@app.route('/api/results/bounce/<batch_id>', methods=['GET'])
def get_bounce_batch_results(batch_id):
    """Get bounce verification results for a specific batch."""
    results = results_service.get_bounce_batch_results(batch_id)
    
    if results:
        return jsonify(results)
    else:
        return jsonify({'error': 'Batch not found'}), 404

# Statistics endpoints
@app.route('/api/statistics', methods=['GET'])
def get_global_statistics():
    """Get global verification statistics."""
    statistics = statistics_service.get_global_statistics()
    return jsonify(statistics)

@app.route('/api/statistics/history/email', methods=['GET'])
def get_email_history():
    """Get verification history for a specific email."""
    email = request.args.get('email')
    
    if not email:
        return jsonify({'error': 'Email parameter is required'}), 400
    
    history = statistics_service.get_email_history(email)
    
    if history:
        return jsonify(history)
    else:
        return jsonify({'error': 'No history found for this email'}), 404

@app.route('/api/statistics/history', methods=['GET'])
def get_verification_history():
    """Get verification history filtered by category."""
    category = request.args.get('category')
    
    if not category:
        return jsonify({'error': 'Category parameter is required'}), 400
    
    history = statistics_service.get_category_history(category)
    
    if history:
        return jsonify(history)
    else:
        return jsonify({'error': 'No history found for this category'}), 404

# Settings endpoints
@app.route('/api/settings', methods=['GET'])
def get_settings():
    """Get all settings."""
    settings = settings_service.get_all_settings()
    return jsonify(settings)

@app.route('/api/settings', methods=['PUT'])
def update_settings():
    """Update settings."""
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'Settings data is required'}), 400
    
    result = settings_service.update_settings(data)
    
    if result['success']:
        return jsonify(result)
    else:
        return jsonify(result), 400

if __name__ == '__main__':
    # Create static directory if it doesn't exist
    os.makedirs(os.path.join(os.path.dirname(__file__), 'static'), exist_ok=True)
    app.run(debug=True, host='0.0.0.0', port=5000)
