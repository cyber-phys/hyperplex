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

def execute_sql(conn, sql, params=None, commit=False, fetchone=False, fetchall=False):
    """Execute SQL commands with optional commit and fetchone, now supports SQL parameters."""
    try:
        c = conn.cursor()
        if params:
            c.execute(sql, params)
        else:
            c.execute(sql)
        if commit:
            conn.commit()
        if fetchone:
            return c.fetchone()
        if fetchall:
            return c.fetchall()
    except Error as e:
        print(f"Error executing SQL: {e}")
        if "UNIQUE constraint failed" in str(e):
            print("Failed parameters:", params)

def create_database(db_file):
    """Create a SQLite database and tables for conversations, chats, embeddings, laws, pdfs and topics"""
    conn = connect_db(db_file)
    if conn is not None:

        # Law Entries Table
        execute_sql(conn, '''
            CREATE TABLE IF NOT EXISTS law_entries (
                uuid TEXT PRIMARY KEY,
                code TEXT,
                title TEXT,
                title_italic TEXT,
                division TEXT,
                division_italic TEXT,
                part TEXT,
                part_italic TEXT,
                chapter TEXT,
                chapter_italic TEXT,
                article TEXT,
                article_italic TEXT,
                section TEXT,
                section_italic TEXT,
                provisions TEXT,
                provisions_italic TEXT,
                text TEXT,
                text_italic TEXT,
                url TEXT
            );
        ''')

        # PDF Entries Table
        execute_sql(conn, '''
            CREATE TABLE IF NOT EXISTS pdf_entries (
                uuid TEXT PRIMARY KEY,
                title TEXT,
                text TEXT,
                type TEXT,
                url TEXT
            );
        ''')

        # Table which holds list of NLP embedding models
        execute_sql(conn, '''
            CREATE TABLE IF NOT EXISTS nlp_model (
                uuid TEXT PRIMARY KEY,
                model TEXT NOT NULL,
                label TEXT NOT NULL UNIQUE,
                chunking_method TEXT CHECK(chunking_method IN ('sentence', 'word', 'char')) NOT NULL,
                chunking_size INTEGER NOT NULL
            );
        ''')

        #TODO make this work with chats and pdfs
        # Table for embeddings 
        execute_sql(conn, '''
            CREATE TABLE IF NOT EXISTS embeddings (
                uuid TEXT PRIMARY KEY,
                model_uuid TEXT NOT NULL,
                law_entry_uuid TEXT NOT NULL,
                creation_time TEXT NOT NULL,
                char_start INTEGER NOT NULL,
                char_end INTEGER NOT NULL,
                embedding BLOB NOT NULL,
                FOREIGN KEY(model_uuid) REFERENCES nlp_model(uuid),
                FOREIGN KEY(law_entry_uuid) REFERENCES law_entries(uuid)
            );
        ''')

        #TODO make general and merge with topics
        # Table for BERTopic labels
        execute_sql(conn, '''
            CREATE TABLE IF NOT EXISTS labels (
                label_uuid TEXT UNIQUE,
                label TEXT NOT NULL,
                creation_time TEXT NOT NULL,
                color TEXT DEFAULT 'blue',
                is_user_label BOOLEAN NOT NULL DEFAULT 0,
                bert_id INTEGER PRIMARY KEY AUTOINCREMENT
            );
        ''')

        # Topics table
        execute_sql(conn, '''
            CREATE TABLE IF NOT EXISTS topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                description TEXT,
                gnn_label TEXT,
                color TEXT DEFAULT 'blue',
                is_user_topic BOOLEAN NOT NULL DEFAULT 0
            );
        ''')

        #TODO: make general and merge with pdf and chats
        # Table that links law entries to labels
        execute_sql(conn, '''
            CREATE TABLE IF NOT EXISTS cluster_label_link (
                label_uuid TEXT NOT NULL,
                law_entry_uuid TEXT NOT NULL,
                creation_time TEXT NOT NULL,
                FOREIGN KEY(label_uuid) REFERENCES labels(label_uuid),
                FOREIGN KEY(law_entry_uuid) REFERENCES law_entries(uuid)
            );
        ''')

        #TODO: make general and merge with pdf and chats
        # Table that links law embeddings to a label
        execute_sql(conn, '''
            CREATE TABLE IF NOT EXISTS label_embeddings (
                label_uuid TEXT NOT NULL,
                law_entry_uuid TEXT NOT NULL,
                creation_time TEXT NOT NULL,
                char_start INTEGER NOT NULL,
                char_end INTEGER NOT NULL,
                embedding BLOB NOT NULL,
                model_uuid TEXT NOT NULL,
                FOREIGN KEY(label_uuid) REFERENCES labels(label_uuid),
                FOREIGN KEY(law_entry_uuid) REFERENCES law_entries(uuid),
                FOREIGN KEY(model_uuid) REFERENCES nlp_model(uuid)
            );
        ''')

        #TODO: make general for use with pdfs and chats
        # Table that links user labels to specific laws + label meta data
        execute_sql(conn, '''
            CREATE TABLE IF NOT EXISTS user_label_texts (
                label_uuid TEXT NOT NULL,
                text_uuid TEXT NOT NULL,
                creation_time TEXT NOT NULL,
                char_start INTEGER NOT NULL,
                char_end INTEGER NOT NULL,
                FOREIGN KEY(label_uuid) REFERENCES labels(label_uuid),
                FOREIGN KEY(text_uuid) REFERENCES law_entries(uuid)
            );
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

def find_duplicate_law_entries(db_file):
    """Find and print the number of duplicate entries in the law_entries table that share the same text."""
    conn = connect_db(db_file)
    if conn is not None:
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT text, COUNT(*) c FROM law_entries 
                GROUP BY section, text, url
                HAVING c > 1;
            ''')
            duplicates = cursor.fetchall()
            num_duplicates = sum(count - 1 for _, count in duplicates)
            print(f"Number of duplicate law entries: {num_duplicates}")
        except Error as e:
            conn.rollback()
            print(f"Error finding duplicate law entries: {e}")
        finally:
            conn.close()
    else:
        print("Failed to connect to the database.")

def clear_labels(db_file):
    """Clear entries from specified tables and print the number of entries before and after clearing."""
    conn = connect_db(db_file)
    if conn is not None:
        try:
            # Begin transaction
            conn.execute('BEGIN')
            
            # Tables to clear
            tables_to_clear = [
                'topics', 'cluster_label_link', 'chat_topics', 
                'conversation_topics', 'topic_hierarchy', 
                'label_embeddings', 'labels'
            ]
            
            # Count entries before clearing
            print("Entries before clearing:")
            for table in tables_to_clear:
                count = conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                print(f"{table}: {count}")
            
            # Delete entries from the tables
            for table in tables_to_clear:
                execute_sql(conn, f'DELETE FROM {table};')
            
            # Commit transaction
            conn.commit()
            
            # Count entries after clearing
            print("\nEntries after clearing:")
            for table in tables_to_clear:
                count = conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                print(f"{table}: {count}")
            
            print("Labels and related entries cleared successfully.")
        except Error as e:
            # Rollback on error
            conn.rollback()
            print(f"Error clearing labels and related entries: {e}")
        finally:
            # Close the connection
            conn.close()
    else:
        print("Failed to connect to the database.")

def deduplicate_law_entries(db_file):
    """Remove duplicate entries from the law_entries table based on text and clean up related tables."""
    conn = connect_db(db_file)
    if conn is not None:
        try:
            conn.execute('BEGIN')

            # Find duplicate texts and their uuids, excluding the first entry for each text
            duplicates_query = '''
                SELECT uuid FROM law_entries
                WHERE rowid NOT IN (
                    SELECT MIN(rowid) FROM law_entries GROUP BY text
                )
            '''
            duplicates_uuids = [row[0] for row in conn.execute(duplicates_query)]

            # Define batch size (SQLite default limit is 999)
            batch_size = 900  # Use a number less than 999 to be safe

            # Function to delete in batches
            def delete_in_batches(uuids, table):
                for i in range(0, len(uuids), batch_size):
                    batch_uuids = uuids[i:i + batch_size]
                    placeholders = ','.join('?' * len(batch_uuids))
                    conn.execute(f'DELETE FROM {table} WHERE law_entry_uuid IN ({placeholders})', batch_uuids)

            # if duplicates_uuids:
            #     # Delete related entries from referencing tables in batches
            #     referencing_tables = [
            #         'embeddings'
            #     ]
            #     for table in referencing_tables:
            #         delete_in_batches(duplicates_uuids, table)

            #     # Delete the duplicate law entries in batches
            #     delete_in_batches(duplicates_uuids, 'law_entries')

            conn.commit()
            print(f"Deduplication complete. Removed {len(duplicates_uuids)} duplicates and related entries.")
        except Error as e:
            conn.rollback()
            print(f"Error during deduplication: {e}")
        finally:
            conn.close()
    else:
        print("Failed to connect to the database.")

def init_database(db_file):
    """Initialize the database with the required tables."""
    create_database(db_file)
    print("Database initialized.")

def add_uuid_to_embeddings(db_file):
    """Add a uuid column to the embeddings table and generate UUIDs for each entry."""
    conn = sqlite3.connect(db_file)
    try:
        # Add a new uuid column
        conn.execute('ALTER TABLE embeddings ADD COLUMN uuid TEXT;')
        conn.commit()

        # Generate and update UUIDs for each row
        cursor = conn.cursor()
        cursor.execute('SELECT rowid FROM embeddings;')
        rows = cursor.fetchall()
        for row in rows:
            new_uuid = str(uuid.uuid4())
            conn.execute('UPDATE embeddings SET uuid = ? WHERE rowid = ?;', (new_uuid, row[0]))
        conn.commit()
        print("UUIDs added to all embeddings entries.")

    except Error as e:
        conn.rollback()
        print(f"Error updating embeddings table with UUIDs: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Database management.')
    parser.add_argument('--clear-labels', action='store_true', help='Clear all label-related entries from the database.')
    parser.add_argument('--check-duplicates', action='store_true', help='Check for duplicate law entries in the law_entries table.')
    parser.add_argument('--deduplicate', action='store_true', help='Remove duplicate entries from the law_entries table.')
    parser.add_argument('--db-file', type=str, help='Path to the SQLite database file.', required=True)
    parser.add_argument('--init-db', action='store_true', help='Initialize the database with required tables.')
    parser.add_argument('--add-uuid', action='store_true', help='Add UUIDs to the embeddings table.')

    
    args = parser.parse_args()
    
    if args.clear_labels:
        clear_labels(args.db_file)
    if args.check_duplicates:
        find_duplicate_law_entries(args.db_file)
    if args.deduplicate:
        deduplicate_law_entries(args.db_file)
    if args.init_db:
        init_database(args.db_file)
    if args.add_uuid:
        add_uuid_to_embeddings(args.db_file)