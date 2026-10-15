import sqlite3, os
DB_PATH = os.environ.get("TIJING_DB", os.path.join(os.path.dirname(__file__), "..", "data", "tijing.db"))
SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, pw_hash TEXT NOT NULL, is_admin INTEGER DEFAULT 0, created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS papers(id INTEGER PRIMARY KEY, title TEXT, exam_date TEXT, source_q TEXT UNIQUE, source_a TEXT, kind TEXT DEFAULT 'objective', duration_min INTEGER DEFAULT 120, qcount INTEGER DEFAULT 0, imported TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS materials(id INTEGER PRIMARY KEY, paper_id INTEGER, text TEXT);
CREATE TABLE IF NOT EXISTS questions(id INTEGER PRIMARY KEY, paper_id INTEGER, num INTEGER, module TEXT, qtype TEXT DEFAULT 'single', stem TEXT, material_id INTEGER, answer TEXT, analysis TEXT, auto_grade INTEGER DEFAULT 1, parse_flags TEXT);
CREATE INDEX IF NOT EXISTS q_paper ON questions(paper_id); CREATE INDEX IF NOT EXISTS q_mod ON questions(module);
CREATE TABLE IF NOT EXISTS options(id INTEGER PRIMARY KEY, question_id INTEGER, label TEXT, text TEXT);
CREATE INDEX IF NOT EXISTS o_q ON options(question_id);
CREATE TABLE IF NOT EXISTS images(id INTEGER PRIMARY KEY, question_id INTEGER, material_id INTEGER, role TEXT, path TEXT, ord INTEGER);
CREATE INDEX IF NOT EXISTS i_q ON images(question_id); CREATE INDEX IF NOT EXISTS i_m ON images(material_id);
CREATE TABLE IF NOT EXISTS attempts(id INTEGER PRIMARY KEY, user_id INTEGER, question_id INTEGER, chosen TEXT, correct INTEGER, mode TEXT, ts TEXT DEFAULT (datetime('now','localtime')));
CREATE INDEX IF NOT EXISTS a_u ON attempts(user_id);
CREATE TABLE IF NOT EXISTS wrongbook(user_id INTEGER, question_id INTEGER, wrong_count INTEGER DEFAULT 0, mastered INTEGER DEFAULT 0, manual INTEGER DEFAULT 0, updated TEXT DEFAULT (datetime('now','localtime')), PRIMARY KEY(user_id,question_id));
CREATE TABLE IF NOT EXISTS exams(id INTEGER PRIMARY KEY, user_id INTEGER, paper_id INTEGER, started TEXT DEFAULT (datetime('now','localtime')), deadline REAL, submitted TEXT, answers TEXT DEFAULT '{}', score INTEGER, total INTEGER, report TEXT);
CREATE TABLE IF NOT EXISTS import_log(id INTEGER PRIMARY KEY, ts TEXT DEFAULT (datetime('now','localtime')), report TEXT);
"""
def conn():
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL"); c.execute("PRAGMA foreign_keys=ON")
    return c
def init():
    c = conn(); c.executescript(SCHEMA); c.commit(); return c
