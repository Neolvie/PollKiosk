# Database module for Poll Kiosk
# SQLite operations for polls, surveys, votes

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
        conn.execute('PRAGMA foreign_keys = ON')
        return conn

    def init_db(self):
        """Initialize database schema"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Polls table (individual questions with answer options)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS polls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                answers TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Surveys table (named collections of polls)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS surveys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Survey-to-polls mapping with ordering
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS survey_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                survey_id INTEGER NOT NULL,
                poll_id INTEGER NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (survey_id) REFERENCES surveys(id) ON DELETE CASCADE,
                FOREIGN KEY (poll_id) REFERENCES polls(id) ON DELETE CASCADE
            )
        ''')

        # Active surveys queue with ordering (multiple surveys can be active)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS active_surveys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                survey_id INTEGER NOT NULL UNIQUE,
                position INTEGER NOT NULL DEFAULT 0,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (survey_id) REFERENCES surveys(id) ON DELETE CASCADE
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

        # Indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_votes_poll_id ON votes(poll_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_survey_questions_survey ON survey_questions(survey_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_active_surveys_pos ON active_surveys(position)')

        conn.commit()
        conn.close()

    # ------------------------------------------------------------------ polls

    def create_poll(self, question, answers):
        """Create a new standalone poll (question with answers)"""
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
        return [
            {
                'id': r['id'],
                'question': r['question'],
                'answers': json.loads(r['answers']),
                'created_at': r['created_at']
            }
            for r in rows
        ]

    def delete_poll(self, poll_id):
        """Delete a poll and all its votes"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM polls WHERE id = ?', (poll_id,))
        conn.commit()
        conn.close()

    # ---------------------------------------------------------------- surveys

    def create_survey(self, title, poll_ids):
        """Create a survey with ordered list of poll IDs"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('INSERT INTO surveys (title) VALUES (?)', (title,))
        survey_id = cursor.lastrowid
        for pos, poll_id in enumerate(poll_ids):
            cursor.execute(
                'INSERT INTO survey_questions (survey_id, poll_id, position) VALUES (?, ?, ?)',
                (survey_id, poll_id, pos)
            )
        conn.commit()
        conn.close()
        return survey_id

    def update_survey(self, survey_id, title, poll_ids):
        """Replace survey title and its question list"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE surveys SET title = ? WHERE id = ?', (title, survey_id))
        cursor.execute('DELETE FROM survey_questions WHERE survey_id = ?', (survey_id,))
        for pos, poll_id in enumerate(poll_ids):
            cursor.execute(
                'INSERT INTO survey_questions (survey_id, poll_id, position) VALUES (?, ?, ?)',
                (survey_id, poll_id, pos)
            )
        conn.commit()
        conn.close()

    def get_survey(self, survey_id):
        """Get survey with its ordered polls"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM surveys WHERE id = ?', (survey_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None
        survey = {'id': row['id'], 'title': row['title'], 'created_at': row['created_at']}
        cursor.execute('''
            SELECT p.id, p.question, p.answers, p.created_at, sq.position
            FROM survey_questions sq
            JOIN polls p ON p.id = sq.poll_id
            WHERE sq.survey_id = ?
            ORDER BY sq.position
        ''', (survey_id,))
        survey['polls'] = [
            {
                'id': r['id'],
                'question': r['question'],
                'answers': json.loads(r['answers']),
                'created_at': r['created_at'],
                'position': r['position']
            }
            for r in cursor.fetchall()
        ]
        conn.close()
        return survey

    def get_all_surveys(self):
        """Get all surveys with poll count"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT s.id, s.title, s.created_at, COUNT(sq.id) as poll_count
            FROM surveys s
            LEFT JOIN survey_questions sq ON sq.survey_id = s.id
            GROUP BY s.id
            ORDER BY s.created_at DESC
        ''')
        rows = cursor.fetchall()
        conn.close()
        return [
            {'id': r['id'], 'title': r['title'], 'created_at': r['created_at'], 'poll_count': r['poll_count']}
            for r in rows
        ]

    def delete_survey(self, survey_id):
        """Delete a survey (cascade deletes survey_questions and active_surveys entries)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM surveys WHERE id = ?', (survey_id,))
        conn.commit()
        conn.close()

    # --------------------------------------------------------- active surveys

    def get_active_surveys(self):
        """Return ordered list of active surveys with their polls"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT s.id, s.title, s.created_at, a.position
            FROM active_surveys a
            JOIN surveys s ON s.id = a.survey_id
            ORDER BY a.position
        ''')
        rows = cursor.fetchall()
        conn.close()
        result = []
        for r in rows:
            survey = self.get_survey(r['id'])
            if survey:
                survey['active_position'] = r['position']
                result.append(survey)
        return result

    def set_active_surveys(self, survey_ids):
        """Replace the entire active surveys queue with given ordered list of survey IDs"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM active_surveys')
        for pos, sid in enumerate(survey_ids):
            cursor.execute(
                'INSERT INTO active_surveys (survey_id, position) VALUES (?, ?)',
                (sid, pos)
            )
        conn.commit()
        conn.close()

    def get_active_survey_ids(self):
        """Return ordered list of active survey IDs"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT survey_id FROM active_surveys ORDER BY position')
        ids = [r['survey_id'] for r in cursor.fetchall()]
        conn.close()
        return ids

    # ------------------------------------------------------------------ votes

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

        cursor.execute('SELECT COUNT(*) as total FROM votes WHERE poll_id = ?', (poll_id,))
        total_votes = cursor.fetchone()['total']

        cursor.execute('''
            SELECT answer_index, COUNT(*) as count
            FROM votes WHERE poll_id = ?
            GROUP BY answer_index ORDER BY answer_index
        ''', (poll_id,))
        answer_counts = {r['answer_index']: r['count'] for r in cursor.fetchall()}

        cursor.execute('''
            SELECT answer_index, ip_address, voted_at
            FROM votes WHERE poll_id = ?
            ORDER BY voted_at DESC LIMIT 20
        ''', (poll_id,))
        recent_votes = [
            {'answer_index': r['answer_index'], 'ip_address': r['ip_address'], 'voted_at': r['voted_at']}
            for r in cursor.fetchall()
        ]
        conn.close()
        return {'total_votes': total_votes, 'answer_counts': answer_counts, 'recent_votes': recent_votes}

    def get_survey_stats(self, survey_id):
        """Get aggregated stats for all polls in a survey"""
        survey = self.get_survey(survey_id)
        if not survey:
            return None
        result = []
        for poll in survey['polls']:
            stats = self.get_poll_stats(poll['id'])
            result.append({'poll': poll, 'stats': stats})
        return result
