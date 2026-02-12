# Poll Kiosk Backend - Flask Application
# Simple Flask backend with SQLite and HTTP Basic Auth

from flask import Flask, render_template, request, jsonify, make_response
from functools import wraps
import json
import os
from datetime import datetime
from database import Database

app = Flask(__name__)

# Определяем путь к базе данных
db_path = os.path.join('data', 'polls.db') if os.path.exists('data') else 'polls.db'
db = Database(db_path)

# Load configuration
def load_config():
    if os.path.exists('config.json'):
        with open('config.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        'admin_username': 'admin',
        'admin_password': 'changeme',
        'current_poll_id': None
    }

def save_config(config):
    with open('config.json', 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

config = load_config()

# HTTP Basic Auth decorator
def check_auth(username, password):
    return username == config['admin_username'] and password == config['admin_password']

def authenticate():
    return make_response(
        'Необходима авторизация', 401,
        {'WWW-Authenticate': 'Basic realm="Admin Area"'}
    )

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

# Public routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/current-poll', methods=['GET'])
def get_current_poll():
    """Get currently active poll"""
    poll_id = config.get('current_poll_id')
    if not poll_id:
        return jsonify({'error': 'No active poll'}), 404
    
    poll = db.get_poll(poll_id)
    if not poll:
        return jsonify({'error': 'Poll not found'}), 404
    
    return jsonify(poll)

@app.route('/api/vote', methods=['POST'])
def submit_vote():
    """Submit a vote for the current poll"""
    data = request.get_json()
    
    if not data or 'poll_id' not in data or 'answer_index' not in data:
        return jsonify({'error': 'Invalid request'}), 400
    
    poll_id = data['poll_id']
    answer_index = data['answer_index']
    
    # Verify poll exists and is active
    if poll_id != config.get('current_poll_id'):
        return jsonify({'error': 'Poll is not active'}), 400
    
    poll = db.get_poll(poll_id)
    if not poll:
        return jsonify({'error': 'Poll not found'}), 404
    
    if answer_index < 0 or answer_index >= len(poll['answers']):
        return jsonify({'error': 'Invalid answer index'}), 400
    
    # Save vote
    db.save_vote(poll_id, answer_index, request.remote_addr)
    
    return jsonify({'success': True})

# Admin routes
@app.route('/admin')
@requires_auth
def admin_panel():
    return render_template('admin.html')

@app.route('/api/admin/polls', methods=['GET'])
@requires_auth
def get_polls():
    """Get all polls"""
    polls = db.get_all_polls()
    current_poll_id = config.get('current_poll_id')
    
    return jsonify({
        'polls': polls,
        'current_poll_id': current_poll_id
    })

@app.route('/api/admin/polls', methods=['POST'])
@requires_auth
def create_poll():
    """Create a new poll"""
    data = request.get_json()
    
    if not data or 'question' not in data or 'answers' not in data:
        return jsonify({'error': 'Invalid request'}), 400
    
    question = data['question'].strip()
    answers = [a.strip() for a in data['answers'] if a.strip()]
    
    if not question or len(answers) < 2:
        return jsonify({'error': 'Question and at least 2 answers required'}), 400
    
    poll_id = db.create_poll(question, answers)
    
    return jsonify({
        'success': True,
        'poll_id': poll_id
    })

@app.route('/api/admin/polls/<int:poll_id>', methods=['DELETE'])
@requires_auth
def delete_poll(poll_id):
    """Delete a poll"""
    # Don't allow deleting active poll
    if poll_id == config.get('current_poll_id'):
        return jsonify({'error': 'Cannot delete active poll'}), 400
    
    db.delete_poll(poll_id)
    return jsonify({'success': True})

@app.route('/api/admin/set-current-poll', methods=['POST'])
@requires_auth
def set_current_poll():
    """Set the currently active poll"""
    data = request.get_json()
    
    if not data or 'poll_id' not in data:
        return jsonify({'error': 'Invalid request'}), 400
    
    poll_id = data['poll_id']
    
    if poll_id is not None:
        poll = db.get_poll(poll_id)
        if not poll:
            return jsonify({'error': 'Poll not found'}), 404
    
    config['current_poll_id'] = poll_id
    save_config(config)
    
    return jsonify({'success': True})

@app.route('/api/admin/stats/<int:poll_id>', methods=['GET'])
@requires_auth
def get_poll_stats(poll_id):
    """Get statistics for a specific poll"""
    poll = db.get_poll(poll_id)
    if not poll:
        return jsonify({'error': 'Poll not found'}), 404
    
    stats = db.get_poll_stats(poll_id)
    
    return jsonify({
        'poll': poll,
        'stats': stats
    })

if __name__ == '__main__':
    # Create default config if doesn't exist
    if not os.path.exists('config.json'):
        save_config(config)
        print("Created default config.json")
        print(f"Default admin credentials: admin / changeme")
    
    # Создать папку data если не существует
    if not os.path.exists('data'):
        os.makedirs('data')
        print("Created data directory")
    
    # Запускаем на 0.0.0.0 чтобы было доступно извне
    app.run(host='0.0.0.0', port=5000, debug=False)
