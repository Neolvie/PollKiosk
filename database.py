# Database module for Poll Kiosk
# SQLite operations for polls and votes

import sqlite3
from datetime import datetime
import json

class Database:
    def __init__(self, db_path='polls.db'):
        self.db_path = db_path
        self.init_db()
    
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_db(self):
        """Initialize database schema"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Polls table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS polls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                answers TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Votes table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                poll_id INTEGER NOT NULL,
                answer_index INTEGER NOT NULL,
                ip_address TEXT,
                voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (poll_id) REFERENCES polls(id) ON DELETE CASCADE
            )
        ''')
        
        # Create index for faster stats queries
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_votes_poll_id 
            ON votes(poll_id)
        ''')
        
        conn.commit()
        conn.close()
    
    def create_poll(self, question, answers):
        """Create a new poll"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        answers_json = json.dumps(answers, ensure_ascii=False)
        
        cursor.execute(
            'INSERT INTO polls (question, answers) VALUES (?, ?)',
            (question, answers_json)
        )
        
        poll_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return poll_id
    
    def get_poll(self, poll_id):
        """Get a specific poll by ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM polls WHERE id = ?', (poll_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return {
            'id': row['id'],
            'question': row['question'],
            'answers': json.loads(row['answers']),
            'created_at': row['created_at']
        }
    
    def get_all_polls(self):
        """Get all polls"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM polls ORDER BY created_at DESC')
        rows = cursor.fetchall()
        conn.close()
        
        polls = []
        for row in rows:
            polls.append({
                'id': row['id'],
                'question': row['question'],
                'answers': json.loads(row['answers']),
                'created_at': row['created_at']
            })
        
        return polls
    
    def delete_poll(self, poll_id):
        """Delete a poll and all its votes"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM polls WHERE id = ?', (poll_id,))
        conn.commit()
        conn.close()
    
    def save_vote(self, poll_id, answer_index, ip_address=None):
        """Save a vote"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            'INSERT INTO votes (poll_id, answer_index, ip_address) VALUES (?, ?, ?)',
            (poll_id, answer_index, ip_address)
        )
        
        conn.commit()
        conn.close()
    
    def get_poll_stats(self, poll_id):
        """Get statistics for a poll"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Get total votes
        cursor.execute(
            'SELECT COUNT(*) as total FROM votes WHERE poll_id = ?',
            (poll_id,)
        )
        total_votes = cursor.fetchone()['total']
        
        # Get votes per answer
        cursor.execute('''
            SELECT answer_index, COUNT(*) as count
            FROM votes
            WHERE poll_id = ?
            GROUP BY answer_index
            ORDER BY answer_index
        ''', (poll_id,))
        
        answer_counts = {}
        for row in cursor.fetchall():
            answer_counts[row['answer_index']] = row['count']
        
        # Get recent votes (last 20)
        cursor.execute('''
            SELECT answer_index, ip_address, voted_at
            FROM votes
            WHERE poll_id = ?
            ORDER BY voted_at DESC
            LIMIT 20
        ''', (poll_id,))
        
        recent_votes = []
        for row in cursor.fetchall():
            recent_votes.append({
                'answer_index': row['answer_index'],
                'ip_address': row['ip_address'],
                'voted_at': row['voted_at']
            })
        
        conn.close()
        
        return {
            'total_votes': total_votes,
            'answer_counts': answer_counts,
            'recent_votes': recent_votes
        }

if __name__ == '__main__':
    # Test database
    db = Database('test.db')
    
    # Create sample poll
    poll_id = db.create_poll(
        "Какой функционал Directum Ario наиболее важен?",
        [
            "Автоматическая классификация",
            "Извлечение данных",
            "Интеллектуальная маршрутизация",
            "OCR"
        ]
    )
    
    print(f"Created poll with ID: {poll_id}")
    
    # Add sample votes
    db.save_vote(poll_id, 0, "192.168.1.1")
    db.save_vote(poll_id, 1, "192.168.1.2")
    db.save_vote(poll_id, 0, "192.168.1.3")
    
    # Get stats
    stats = db.get_poll_stats(poll_id)
    print(f"Stats: {stats}")
