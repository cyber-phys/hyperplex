import json
import sqlite3
from sqlite3 import Error
from functools import partial, reduce
import uuid
from typing import Dict, List, Tuple
import pandas as pd
import argparse

def connect_db(db_file):
    """Attempt to connect to the SQLite database and return the connection object."""
    try:
        conn = sqlite3.connect(db_file)
        return conn
    except Error as e:
        print(f"Error connecting to database: {e}")
        return None

def execute_sql(conn, sql, params=None, commit=False):
    """Execute SQL commands with optional commit, now supports SQL parameters."""
    try:
        c = conn.cursor()
        if params:
            c.execute(sql, params)
        else:
            c.execute(sql)
        if commit:
            conn.commit()
    except Error as e:
        print(f"Error executing SQL: {e}")
        if "UNIQUE constraint failed" in str(e):
            print("Failed parameters:", params)

def create_database(db_file):
    """Create a SQLite database and tables for conversations, chats, and topics."""
    conn = connect_db(db_file)
    if conn is not None:

        # Law Entries Table
        execute_sql(conn, '''
            CREATE TABLE IF NOT EXISTS law_entries (
                uuid TEXT PRIMARY KEY,
                code TEXT,
                section REAL,
                text TEXT,
                amended TEXT,
                url TEXT
        ''')

        # Conversations table
        execute_sql(conn, '''
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT UNIQUE PRIMARY KEY,
                title TEXT,
                create_time TEXT,
                update_time TEXT,
                is_archived BOOLEAN
            );
        ''')

        # Chats table
        execute_sql(conn, '''
            CREATE TABLE IF NOT EXISTS chats (
                id TEXT UNIQUE PRIMARY KEY,
                conversation_id TEXT,
                content_type TEXT,
                model TEXT,
                message TEXT,
                author TEXT,
                create_time TEXT,
                status TEXT,
                recipient TEXT,
                parent TEXT,
                is_first_message BOOLEAN,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            );
        ''')

        # Topics table
        execute_sql(conn, '''
            CREATE TABLE IF NOT EXISTS topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                description TEXT,
                gnn_label TEXT
            );
        ''')

        # Chat topics table
        execute_sql(conn, '''
            CREATE TABLE IF NOT EXISTS chat_topics (
                chat_id TEXT,
                topic_id INTEGER,
                FOREIGN KEY (chat_id) REFERENCES chats(id),
                FOREIGN KEY (topic_id) REFERENCES topics(id)
            );
        ''')

        # Chat links table
        execute_sql(conn, '''
            CREATE TABLE IF NOT EXISTS chat_links (
                source_chat_id TEXT,
                target_chat_id TEXT,
                topic_id INTEGER,
                FOREIGN KEY (source_chat_id) REFERENCES chats(id),
                FOREIGN KEY (target_chat_id) REFERENCES chats(id),
                FOREIGN KEY (topic_id) REFERENCES topics(id)
            );
        ''')

        # Conversation topics table
        execute_sql(conn, '''
            CREATE TABLE IF NOT EXISTS conversation_topics (
                conversation_id TEXT,
                topic_id INTEGER,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id),
                FOREIGN KEY (topic_id) REFERENCES topics(id)
            );
        ''')

        # Topics hierarchy table
        execute_sql(conn, '''
            CREATE TABLE IF NOT EXISTS topic_hierarchy (
                parent_topic_id INTEGER,
                child_topic_id INTEGER,
                FOREIGN KEY (parent_topic_id) REFERENCES topics(id),
                FOREIGN KEY (child_topic_id) REFERENCES topics(id),
                PRIMARY KEY (parent_topic_id, child_topic_id)
            );
        ''')

        # Preicted chat links table
        execute_sql(conn, '''
            CREATE TABLE IF NOT EXISTS predicted_chat_links (
                source_chat_id TEXT,
                target_chat_id TEXT,
                score REAL,
                FOREIGN KEY (source_chat_id) REFERENCES chats(id),
                FOREIGN KEY (target_chat_id) REFERENCES chats(id)
            );
        ''', commit=True)

        conn.close()
        print("Database and tables created successfully.")