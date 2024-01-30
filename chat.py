import json
import sqlite3
from sqlite3 import Error
from functools import partial

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
                description TEXT
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
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        ''', commit=True)

        conn.close()
        print("Database and tables created successfully.")

def parse_json(file_path):
    with open(file_path, 'r') as f:
        data = json.load(f)

    def process_chat(chat_data, conversation_id, first_entry_id):
        is_first_message = (chat_data["id"] == first_entry_id)
        message_text = []
        model = "unknown"
        content_type = chat_data["message"]["content"]["content_type"] if chat_data["message"] else "unknown"
        role = chat_data["message"]["author"]["role"] if chat_data["message"] else "unknown"

        if role == "user":
            model = "user"
        elif role == "assistant":
            model = chat_data["message"]["metadata"].get("model_slug", "gpt-3.5") if chat_data["message"] else "unknown"
        elif role == "tool":
            model = chat_data["message"]["metadata"]["model_slug"] if chat_data["message"] else "unknown"

        if content_type in ["text", "multimodal_text"]:
            message_parts = chat_data["message"]["content"].get("parts", []) if chat_data["message"] else []
            message_text = [part for part in message_parts if isinstance(part, str)]
        elif role == "tool" and "result" in chat_data["message"]["content"]:
            message_text = [chat_data["message"]["content"]["result"]]
        elif chat_data["message"] is None:
            message_text = ""
        elif "text" in chat_data["message"]["content"]:
            message_text = [chat_data["message"]["content"]["text"]]
        else:
            print(chat_data)


        if message_text:
            return {
                "id": chat_data["id"],
                "content_type": content_type,
                "model": model,
                "message": message_text,
                "author": role,
                "create_time": chat_data["message"]["create_time"] if chat_data["message"] else None,
                "status": chat_data["message"]["status"] if chat_data["message"] else "unknown",
                "recipient": chat_data["message"]["recipient"] if chat_data["message"] else "unknown",
                "parent": chat_data["parent"],
                "children": chat_data["children"],
                "conversation_id": conversation_id,
                "is_first_message": is_first_message
            }
        return None

    conversation_infos = []
    all_chats = []

    for conversation in data:
        conversation_info = {
            "id": conversation["id"],
            "title": conversation.get("title", ""),
            "create_time": conversation["create_time"],
            "update_time": conversation["update_time"],
            "is_archived": conversation["is_archived"]
        }
        conversation_infos.append(conversation_info)

        # Find the first chat by checking for a "parent" key with a null value
        first_entry_id = None
        for chat_id, chat_data in conversation["mapping"].items():
            if chat_data.get("parent") is None:
                first_entry_id = chat_id
                break

        # Iterate over the dictionary's values
        for chat_id, chat_data in conversation["mapping"].items():
            chat = process_chat(chat_data, conversation["id"], first_entry_id)
            if chat:
                all_chats.append(chat)

    return conversation_infos, all_chats

def insert_conversations_and_chats(db_file, conversation_infos, all_chats):
    conn = connect_db(db_file)
    if conn is not None:
        insert_conversation_sql = '''
            INSERT INTO conversations (id, title, create_time, update_time, is_archived)
            VALUES (?, ?, ?, ?, ?);
        '''
        insert_chat_sql = '''
            INSERT INTO chats (id, conversation_id, content_type, model, message, author, create_time, status, recipient, parent, is_first_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        '''

        for conversation in conversation_infos:
            execute_sql(conn, insert_conversation_sql, (conversation["id"], conversation["title"], conversation["create_time"], conversation["update_time"], conversation["is_archived"]), commit=True)

        for chat in all_chats:
            execute_sql(conn, insert_chat_sql, (chat["id"], chat["conversation_id"], chat["content_type"], chat["model"], json.dumps(chat["message"]), chat["author"], chat["create_time"], chat["status"], chat["recipient"], chat["parent"], chat["is_first_message"]), commit=True)

        conn.close()
        print("Conversations and chats inserted successfully.")

# Example usage
db_file = 'chat.db'
create_database(db_file)
conversation_infos, all_chats = parse_json('/Users/luc/law/chatgpt_export_12_29_24/conversations.json')
insert_conversations_and_chats(db_file, conversation_infos, all_chats)