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
                multi_select INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Migration: add multi_select if column is missing (existing DBs)
        try:
            cursor.execute('ALTER TABLE polls ADD COLUMN multi_select INTEGER NOT NULL DEFAULT 0')
        except Exception:
            pass

        # Surveys table (named collections of polls)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS surveys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                show_title INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Migration: add show_title if column is missing (existing DBs)
        try:
            cursor.execute('ALTER TABLE surveys ADD COLUMN show_title INTEGER NOT NULL DEFAULT 1')
        except Exception:
            pass

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
                session_id TEXT,
                voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (poll_id) REFERENCES polls(id) ON DELETE CASCADE
            )
        ''')

        # Migration: add session_id if column is missing (existing DBs)
        try:
            cursor.execute('ALTER TABLE votes ADD COLUMN session_id TEXT')
        except Exception:
            pass

        # Indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_votes_poll_id ON votes(poll_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_survey_questions_survey ON survey_questions(survey_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_active_surveys_pos ON active_surveys(position)')

        conn.commit()
        conn.close()

    # ------------------------------------------------------------------ polls

    def create_poll(self, question, answers, multi_select=False):
        """Create a new standalone poll (question with answers)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        answers_json = json.dumps(answers, ensure_ascii=False)
        cursor.execute(
            'INSERT INTO polls (question, answers, multi_select) VALUES (?, ?, ?)',
            (question, answers_json, 1 if multi_select else 0)
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
            'multi_select': bool(row['multi_select']),
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
                'multi_select': bool(r['multi_select']),
                'created_at': r['created_at']
            }
            for r in rows
        ]

    def update_poll(self, poll_id, question, answers, multi_select=None):
        """Update question text and answers; optionally update multi_select flag"""
        conn = self.get_connection()
        cursor = conn.cursor()
        if multi_select is None:
            cursor.execute(
                'UPDATE polls SET question = ?, answers = ? WHERE id = ?',
                (question, json.dumps(answers, ensure_ascii=False), poll_id)
            )
        else:
            cursor.execute(
                'UPDATE polls SET question = ?, answers = ?, multi_select = ? WHERE id = ?',
                (question, json.dumps(answers, ensure_ascii=False), 1 if multi_select else 0, poll_id)
            )
        conn.commit()
        conn.close()

    def delete_poll(self, poll_id):
        """Delete a poll and all its votes"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM polls WHERE id = ?', (poll_id,))
        conn.commit()
        conn.close()

    # ---------------------------------------------------------------- surveys

    def create_survey(self, title, poll_ids, show_title=True):
        """Create a survey with ordered list of poll IDs"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('INSERT INTO surveys (title, show_title) VALUES (?, ?)', (title, 1 if show_title else 0))
        survey_id = cursor.lastrowid
        for pos, poll_id in enumerate(poll_ids):
            cursor.execute(
                'INSERT INTO survey_questions (survey_id, poll_id, position) VALUES (?, ?, ?)',
                (survey_id, poll_id, pos)
            )
        conn.commit()
        conn.close()
        return survey_id

    def update_survey(self, survey_id, title, poll_ids, show_title=None):
        """Replace survey title, show_title flag and its question list"""
        conn = self.get_connection()
        cursor = conn.cursor()
        if show_title is None:
            cursor.execute('UPDATE surveys SET title = ? WHERE id = ?', (title, survey_id))
        else:
            cursor.execute('UPDATE surveys SET title = ?, show_title = ? WHERE id = ?',
                           (title, 1 if show_title else 0, survey_id))
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
        survey = {'id': row['id'], 'title': row['title'], 'show_title': bool(row['show_title']), 'created_at': row['created_at']}
        cursor.execute('''
            SELECT p.id, p.question, p.answers, p.multi_select, p.created_at, sq.position
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
                'multi_select': bool(r['multi_select']),
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
            SELECT s.id, s.title, s.show_title, s.created_at, COUNT(sq.id) as poll_count
            FROM surveys s
            LEFT JOIN survey_questions sq ON sq.survey_id = s.id
            GROUP BY s.id
            ORDER BY s.created_at DESC
        ''')
        rows = cursor.fetchall()
        conn.close()
        return [
            {'id': r['id'], 'title': r['title'], 'show_title': bool(r['show_title']),
             'created_at': r['created_at'], 'poll_count': r['poll_count']}
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

    def save_vote(self, poll_id, answer_indices, ip_address=None, session_id=None):
        """
        Save a vote (one or more answer indices for multi_select questions).
        answer_indices: int OR list[int]
        Each answer_index is stored as a separate row in votes.
        """
        if isinstance(answer_indices, int):
            answer_indices = [answer_indices]
        conn = self.get_connection()
        cursor = conn.cursor()
        for idx in answer_indices:
            cursor.execute(
                'INSERT INTO votes (poll_id, answer_index, ip_address, session_id) VALUES (?, ?, ?, ?)',
                (poll_id, idx, ip_address, session_id)
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

    def get_survey_respondents(self, survey_id):
        """
        Return per-respondent answers for all polls in a survey.
        Result: {
            'polls': [{'id', 'question', 'answers'}, ...],   # ordered
            'rows':  [{'session_id', 'voted_at', 'answers': {poll_id: answer_text}}, ...]
        }
        Rows ordered by first vote time, one row per unique session_id.
        Sessions without a session_id are each treated as a separate anonymous respondent.
        """
        survey = self.get_survey(survey_id)
        if not survey:
            return None

        polls = survey['polls']
        poll_ids = [p['id'] for p in polls]
        if not poll_ids:
            return {'polls': polls, 'rows': []}

        conn = self.get_connection()
        cursor = conn.cursor()
        placeholders = ','.join('?' * len(poll_ids))
        cursor.execute(f'''
            SELECT poll_id, answer_index, session_id, ip_address, voted_at
            FROM votes
            WHERE poll_id IN ({placeholders})
            ORDER BY voted_at
        ''', poll_ids)
        raw = cursor.fetchall()
        conn.close()

        # Build poll lookup
        poll_map = {p['id']: p for p in polls}

        # Group votes into respondent sessions.
        # Priority: use session_id when present.
        # Fallback for legacy anonymous votes (no session_id): group by
        # ip_address within a 10-minute sliding window so that one person
        # answering several questions in a row appears as a single row.
        from collections import OrderedDict
        from datetime import datetime, timedelta

        ANON_WINDOW = timedelta(minutes=10)

        sessions = OrderedDict()   # key -> session dict
        # Track last-vote-time for each (ip, anon_group_key) to merge anon votes
        anon_last: dict = {}       # ip -> (last_voted_at, group_key)
        anon_counter = 0

        for r in raw:
            sid = r['session_id']
            if sid:
                key = sid
            else:
                ip = r['ip_address'] or '__no_ip__'
                try:
                    ts = datetime.fromisoformat(r['voted_at'])
                except Exception:
                    ts = None
                if ip in anon_last and ts is not None:
                    last_ts, existing_key = anon_last[ip]
                    try:
                        last_dt = datetime.fromisoformat(last_ts)
                    except Exception:
                        last_dt = None
                    if last_dt is not None and (ts - last_dt) <= ANON_WINDOW:
                        key = existing_key
                    else:
                        anon_counter += 1
                        key = f'__anon_{anon_counter}__'
                else:
                    anon_counter += 1
                    key = f'__anon_{anon_counter}__'
                anon_last[ip] = (r['voted_at'], key)

            if key not in sessions:
                sessions[key] = {'session_id': key, 'voted_at': r['voted_at'], 'answers': {}}
            pid = r['poll_id']
            idx = r['answer_index']
            poll_obj = poll_map[pid]
            answer_text = poll_obj['answers'][idx] if idx < len(poll_obj['answers']) else '?'
            if pid not in sessions[key]['answers']:
                sessions[key]['answers'][pid] = {
                    'answer_indices': [],
                    'answer_texts': []
                }
            sessions[key]['answers'][pid]['answer_indices'].append(idx)
            sessions[key]['answers'][pid]['answer_texts'].append(answer_text)

        return {'polls': polls, 'rows': list(sessions.values())}

    def reset_survey_votes(self, survey_id):
        """Delete all votes for all polls belonging to a survey."""
        survey = self.get_survey(survey_id)
        if not survey:
            return False
        poll_ids = [p['id'] for p in survey['polls']]
        if not poll_ids:
            return True
        conn = self.get_connection()
        cursor = conn.cursor()
        placeholders = ','.join('?' * len(poll_ids))
        cursor.execute(f'DELETE FROM votes WHERE poll_id IN ({placeholders})', poll_ids)
        conn.commit()
        conn.close()
        return True

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
