import json
import sqlite3
from sqlite3 import Error
from functools import partial, reduce
import uuid
from typing import Dict, List, Tuple
import pandas as pd


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
        ''', commit=True)

        conn.close()
        print("Database and tables created successfully.")

def parse_json(file_path):
    with open(file_path, 'r') as f:
        data = json.load(f)

    def generate_new_uuid_map(chats):
        """Generate a mapping of old IDs to new UUIDs."""
        return {chat["id"]: str(uuid.uuid4()) for chat in chats}

    def apply_new_uuids(chat, uuid_map):
        """Apply new UUIDs to chat and adjust parent references."""
        updated_chat = chat.copy()
        updated_chat["id"] = uuid_map.get(chat["id"], chat["id"])
        if chat["parent"] in uuid_map:
            updated_chat["parent"] = uuid_map[chat["parent"]]
        return updated_chat

    def process_chat(chat_data, conversation_id, first_entry_id, uuid_map):
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

        if chat_data["message"] is not None:
            return apply_new_uuids({
                "id": chat_data["id"],
                "content_type": content_type,
                "model": model,
                "message": message_text if message_text else "",
                "author": role,
                "create_time": chat_data.get("message", {}).get("create_time"),
                "status": chat_data.get("message", {}).get("status", "unknown"),
                "recipient": chat_data.get("message", {}).get("recipient", "unknown"),
                "parent": chat_data["parent"],
                "children": chat_data["children"],
                "conversation_id": conversation_id,
                "is_first_message": is_first_message
            }, uuid_map)
        else: 
            return None

    conversation_infos = []
    all_chats = []

    for conversation in data:
        conversation_chats = list(conversation["mapping"].values())
        uuid_map = generate_new_uuid_map(conversation_chats)

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
            chat = process_chat(chat_data, conversation["id"], first_entry_id, uuid_map)
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

def fetch_table_data(conn, query):
    """Fetch data from a table using a provided SQL query."""
    try:
        cursor = conn.cursor()
        cursor.execute(query)
        columns = [description[0] for description in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    except Error as e:
        print(f"Error fetching data: {e}")
        return []

def fetch_chats(conn):
    """
    Fetch chats from the database, including the topic label name for each chat.
    
    Parameters:
    - conn: The database connection object.
    
    Returns:
    - A list of dictionaries, each representing a chat with an additional 'label' field for the topic label name.
    """
    try:
        cursor = conn.cursor()
        # Modified SQL query to join chats with chat_topics and topics to fetch the topic name as label
        query = """
        SELECT c.id, c.conversation_id, c.content_type, c.model, c.message, c.author, c.create_time, c.status, c.recipient, c.parent, c.is_first_message, t.name AS label
        FROM chats c
        LEFT JOIN chat_topics ct ON c.id = ct.chat_id
        LEFT JOIN topics t ON ct.topic_id = t.id
        """
        cursor.execute(query)
        columns = [description[0] for description in cursor.description]
        # Using list comprehension and dict to ensure the function is deterministic and has no side effects
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    except Error as e:
        print(f"Error fetching chats with topics: {e}")
        return []

def fetch_topics(conn):
    return fetch_table_data(conn, "SELECT * FROM topics")

def fetch_chat_topics(conn):
    """
    Fetch chat topics from the database, including the label name for each chat topic.
    
    Parameters:
    - conn: The database connection object.
    
    Returns:
    - A list of dictionaries, each representing a chat topic with an additional 'label' field for the topic label name.
    """
    try:
        cursor = conn.cursor()
        query = """
        SELECT ct.chat_id, ct.topic_id, t.name AS label
        FROM chat_topics ct
        JOIN topics t ON ct.topic_id = t.id
        """
        cursor.execute(query)
        columns = [description[0] for description in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    except Error as e:
        print(f"Error fetching chat topics with labels: {e}")
        return []

def fetch_topic_links(conn):
    """
    Fetch topic links from the database, including the labels for the parent and child topics.
    
    Parameters:
    - conn: The database connection object.
    
    Returns:
    - A list of dictionaries, each representing a topic link with labels for both parent and child topics.
    """
    try:
        c = conn.cursor()
        query = """
        SELECT 
            th.parent_topic_id, 
            pt.name AS parent_label, 
            th.child_topic_id, 
            ct.name AS child_label
        FROM topic_hierarchy th
        JOIN topics pt ON th.parent_topic_id = pt.id
        JOIN topics ct ON th.child_topic_id = ct.id
        """
        c.execute(query)
        rows = c.fetchall()
        
        # Transform the rows into a list of dictionaries using a list comprehension
        topic_links = [
            {"parent_topic_id": row[0], "parent_label": row[1], "child_topic_id": row[2], "child_label": row[3]}
            for row in rows
        ]
        
        return topic_links
    except Error as e:
        print(f"Error fetching topic links: {e}")
        return []

def fetch_chat_links(conn):
    """
    Fetch chat links from the database, including the topic label name for each chat link, and the authors of the source and target chats.
    Each chat link will also have a UUIDv4 generated as its id.
    
    Parameters:
    - conn: The database connection object.
    
    Returns:
    - A list of dictionaries, each representing a chat link with an additional 'label' field for the topic label name, 'source_author', 'target_author', and a UUIDv4 as 'id'.
    """
    try:
        cursor = conn.cursor()
        # Modified SQL query to join chat_links with topics to fetch the topic name as label, and also join with chats to get the authors
        query = """
        SELECT cl.source_chat_id, cl.target_chat_id, cl.topic_id, t.name AS label, sc.author AS source_author, tc.author AS target_author
        FROM chat_links cl
        JOIN topics t ON cl.topic_id = t.id
        JOIN chats sc ON cl.source_chat_id = sc.id
        JOIN chats tc ON cl.target_chat_id = tc.id
        """
        cursor.execute(query)
        chat_links = cursor.fetchall()
        
        # Generate a UUIDv4 for each chat link and construct the result
        result = [
            {
                "id": str(uuid.uuid4()),
                "source_chat_id": chat_link[0],
                "target_chat_id": chat_link[1],
                "topic_id": chat_link[2],
                "label": chat_link[3],
                "source_author": chat_link[4],
                "target_author": chat_link[5]
            }
            for chat_link in chat_links
        ]
        
        return result
    except Error as e:
        print(f"Error fetching chat links with topics and authors: {e}")
        return []
    
def fetch_conversations(conn):
    """
    Fetch conversations from the database using the fetch_table_data function.
    """
    query = "SELECT id, title, create_time, update_time, is_archived FROM conversations"
    return fetch_table_data(conn, query)

def fetch_chat(conn, chat_id) -> Dict:
    """
    Fetch chat data by chat ID from the database and return it as a dictionary.

    Parameters:
    - conn: The database connection object.
    - chat_id: The ID of the chat to fetch.

    Returns:
    - A dictionary containing the chat data, or None if not found.
    """
    try:
        c = conn.cursor()
        c.execute("SELECT * FROM chats WHERE id = ?", (chat_id,))
        row = c.fetchone()
        if row:
            columns = [col[0] for col in c.description]
            return dict(zip(columns, row))
        return None
    except Error as e:
        print(f"Error fetching chat data: {e}")
        return None

def fetch_all_chats(conn) -> Dict[str, List]:
    """
    Fetch the entire chat history from the database and return it as a dictionary.
    Each key in the dictionary corresponds to a column name, and its value is a list
    of the data from that column across all rows.

    Parameters:
    - conn: The database connection object.

    Returns:
    - A dictionary with column names as keys and lists of column data as values.
    """
    try:
        c = conn.cursor()
        c.execute("SELECT * FROM chats")
        rows = c.fetchall()
        if rows:
            columns = [col[0] for col in c.description]
            # Using a dictionary comprehension to create the desired structure
            # and map to aggregate the column data into lists
            chat_history = {column: [row[idx] for row in rows] for idx, column in enumerate(columns)}
            return chat_history
        return {}
    except Error as e:
        print(f"Error fetching all chat data: {e}")
        return {}

def fetch_conversations_with_chats(conn) -> List[Dict]:
    """
    Fetch chats from the database and return them grouped by conversation_id.
    Each group of chats for a specific conversation_id is represented as a dictionary,
    with keys corresponding to column names and values being lists of data from those columns,
    for all chats belonging to the same conversation_id.

    Parameters:
    - conn: The database connection object.

    Returns:
    - A list of dictionaries, where each dictionary represents all chats for a specific conversation_id.
    """
    try:
        c = conn.cursor()
        c.execute("SELECT * FROM chats ORDER BY conversation_id")
        rows = c.fetchall()
        
        # If no rows are fetched, return an empty list
        if not rows:
            return []

        # Initialize a list to hold dictionaries for each conversation
        conversations = []
        current_conversation_id = None
        conversation_dict = {}

        for row in rows:
            columns = [col[0] for col in c.description]
            chat_dict = dict(zip(columns, row))
            
            # Check if we're still on the same conversation
            if chat_dict['conversation_id'] != current_conversation_id:
                # If not, and if we have a previous conversation, add it to the list
                if conversation_dict:
                    conversations.append(conversation_dict)
                # Start a new conversation dictionary
                current_conversation_id = chat_dict['conversation_id']
                conversation_dict = {col: [] for col in columns}
            
            # Append data from the current row to the appropriate lists in the conversation_dict
            for col in columns:
                conversation_dict[col].append(chat_dict[col])
        
        # Don't forget to add the last conversation to the list
        if conversation_dict:
            conversations.append(conversation_dict)

        return conversations
    except Error as e:
        print(f"Error fetching conversations with chats: {e}")
        return []
    
def fetch_message_pairs(conn) -> Dict[str, List]:
    """
    Fetch all message pairs (parent and child messages) from the database and return
    them as a dictionary with specified keys. Each key in the dictionary corresponds
    to an attribute of the message pairs, and its value is a list of the data for that
    attribute across all message pairs.

    Parameters:
    - conn: The database connection object.

    Returns:
    - A dictionary with attributes as keys and lists of attribute data as values.
    """
    try:
        c = conn.cursor()
        # SQL query to join each chat with its parent and select the required attributes
        query = """
        SELECT
            parent.id AS parent_id,
            child.id AS child_id,
            child.conversation_id,
            child.create_time,
            parent.message || ' ' || child.message AS message,
            parent.author AS parent_author,
            child.author AS child_author,
            parent.model AS parent_model,
            child.model AS child_model
        FROM
            chats AS child
            INNER JOIN chats AS parent ON child.parent = parent.id
        """
        c.execute(query)
        rows = c.fetchall()

        # If we have results, transform them into the desired dictionary format
        if rows:
            # Initialize keys with empty lists
            message_pairs = {
                "parent_id": [],
                "child_id": [],
                "conversation_id": [],
                "creation_time": [],
                "message": [],
                "parent_author": [],
                "child_author": [],
                "parent_model": [],
                "child_model": []
            }

            # Populate the lists with data from each row
            for row in rows:
                message_pairs["parent_id"].append(row[0])
                message_pairs["child_id"].append(row[1])
                message_pairs["conversation_id"].append(row[2])
                message_pairs["creation_time"].append(row[3])
                message_pairs["message"].append(row[4])
                message_pairs["parent_author"].append(row[5])
                message_pairs["child_author"].append(row[6])
                message_pairs["parent_model"].append(row[7])
                message_pairs["child_model"].append(row[8])

            return message_pairs
        return {}
    except Error as e:
        print(f"Error fetching message pairs: {e}")
        return {}
    
def insert_topics(conn, topic_names: List[str]):
    """
    Insert new topics into the database from a list of topic names, ensuring each topic is unique.

    Parameters:
    - conn: The database connection object.
    - topic_names: A list of topic names to insert.
    """
    try:
        c = conn.cursor()
        # Prepare the SQL query to check if a topic already exists
        check_query = "SELECT name FROM topics WHERE name = ?"
        # Prepare the SQL query to insert a new topic
        insert_query = "INSERT INTO topics (name) VALUES (?)"

        for name in topic_names:
            # Check if the topic already exists
            c.execute(check_query, (name,))
            result = c.fetchone()
            if not result:
                # If the topic does not exist, insert it
                c.execute(insert_query, (name,))
        # Commit the transaction to save all the changes
        conn.commit()
        print(f"Unique topics inserted successfully.")
    except Error as e:
        print(f"Error inserting unique topics: {e}")
        # Rollback in case of error
        conn.rollback()

def insert_chat_topics(conn, chat_ids: List[str], topic_names: List[str]):
    """
    Insert new chat topics into the chat_topics table. This function takes in a list of chat_ids and topic_names,
    finds the matching topic_id for each topic_name, and inserts the chat_id and topic_id into the chat_topics table.
    If a topic_name does not exist in the topics table, it is inserted and its new topic_id is used.

    Parameters:
    - conn: The database connection object.
    - chat_ids: A list of chat IDs.
    - topic_names: A list of topic names.

    Note: The function assumes that the lists chat_ids and topic_names are of the same size.
    """
    if len(chat_ids) != len(topic_names):
        print("Error: The lists of chat IDs and topic names must be the same size.")
        return

    try:
        c = conn.cursor()
        for chat_id, topic_name in zip(chat_ids, topic_names):
            # Check if the topic exists and get its ID
            c.execute("SELECT id FROM topics WHERE name = ?", (topic_name,))
            topic_result = c.fetchone()

            if topic_result:
                topic_id = topic_result[0]
            else:
                # Insert the new topic if it doesn't exist
                c.execute("INSERT INTO topics (name) VALUES (?)", (topic_name,))
                topic_id = c.lastrowid  # Get the ID of the newly inserted topic

            # Insert the chat_id and topic_id into chat_topics
            c.execute("INSERT INTO chat_topics (chat_id, topic_id) VALUES (?, ?)", (chat_id, topic_id))

        conn.commit()
        print("Chat topics inserted successfully.")
    except Error as e:
        print(f"Error inserting chat topics: {e}")
        conn.rollback()

def insert_chat_links(conn, source_chat_ids: List[str], target_chat_ids: List[str], topic_names: List[str]):
    """
    Insert new chat links into the chat_links table. This function takes in lists of source_chat_ids, target_chat_ids,
    and topic_names, finds the matching topic_id for each topic_name, and inserts the source_chat_id, target_chat_id,
    and topic_id into the chat_links table. If a topic_name does not exist in the topics table, it is inserted and its
    new topic_id is used.

    Parameters:
    - conn: The database connection object.
    - source_chat_ids: A list of source chat IDs.
    - target_chat_ids: A list of target chat IDs.
    - topic_names: A list of topic names.

    Note: The function assumes that the lists source_chat_ids, target_chat_ids, and topic_names are of the same size.
    """
    if not (len(source_chat_ids) == len(target_chat_ids) == len(topic_names)):
        print("Error: The lists of source chat IDs, target chat IDs, and topic names must be the same size.")
        return

    try:
        c = conn.cursor()
        for source_chat_id, target_chat_id, topic_name in zip(source_chat_ids, target_chat_ids, topic_names):
            # Check if the topic exists and get its ID
            c.execute("SELECT id FROM topics WHERE name = ?", (topic_name,))
            topic_result = c.fetchone()

            if topic_result:
                topic_id = topic_result[0]
            else:
                # Insert the new topic if it doesn't exist
                c.execute("INSERT INTO topics (name) VALUES (?)", (topic_name,))
                topic_id = c.lastrowid  # Get the ID of the newly inserted topic

            # Insert the source_chat_id, target_chat_id, and topic_id into chat_links
            c.execute("INSERT INTO chat_links (source_chat_id, target_chat_id, topic_id) VALUES (?, ?, ?)", (source_chat_id, target_chat_id, topic_id))

        conn.commit()
        print("Chat links inserted successfully.")
    except Error as e:
        print(f"Error inserting chat links: {e}")
        conn.rollback()

def insert_conversation_topics(conn, conversation_id: str, topic_names: List[str]):
    """
    Insert new conversation topics into the conversation_topics table. This function takes in a single conversation_id
    and a list of topic_names, finds the matching topic_id for each topic_name, and inserts the conversation_id and
    topic_id into the conversation_topics table. If a topic_name does not exist in the topics table, it is inserted
    and its new topic_id is used.

    Parameters:
    - conn: The database connection object.
    - conversation_id: A single conversation ID.
    - topic_names: A list of topic names.
    """
    try:
        c = conn.cursor()
        for topic_name in topic_names:
            # Check if the topic exists and get its ID
            c.execute("SELECT id FROM topics WHERE name = ?", (topic_name,))
            topic_result = c.fetchone()

            if topic_result:
                topic_id = topic_result[0]
            else:
                # Insert the new topic if it doesn't exist
                c.execute("INSERT INTO topics (name) VALUES (?)", (topic_name,))
                topic_id = c.lastrowid  # Get the ID of the newly inserted topic

            # Insert the conversation_id and topic_id into conversation_topics
            c.execute("INSERT INTO conversation_topics (conversation_id, topic_id) VALUES (?, ?)", (conversation_id, topic_id))

        conn.commit()
        print("Conversation topics inserted successfully.")
    except Error as e:
        print(f"Error inserting conversation topics: {e}")
        conn.rollback()

def insert_topic_hierarchy(conn, parent_topic_names: List[str], child_topic_names: List[str]):
    """
    Insert new entries into the topic_hierarchy table. This function takes in lists of parent topic_names and child topic_names,
    finds the topic_ids for the parents and children, and inserts them into the table. An error is printed if the lists are not
    the same size or if a match for the topic_id cannot be found.

    Parameters:
    - conn: The database connection object.
    - parent_topic_names: A list of parent topic names.
    - child_topic_names: A list of child topic names.
    """
    if len(parent_topic_names) != len(child_topic_names):
        print("Error: The lists of parent topic names and child topic names must be the same size.")
        return

    try:
        c = conn.cursor()
        for parent_name, child_name in zip(parent_topic_names, child_topic_names):
            # Find or insert the parent topic_id
            c.execute("SELECT id FROM topics WHERE name = ?", (parent_name,))
            parent_result = c.fetchone()
            if parent_result:
                parent_id = parent_result[0]
            else:
                print(f"Error: No match found for parent topic name '{parent_name}'.")
                return

            # Find or insert the child topic_id
            c.execute("SELECT id FROM topics WHERE name = ?", (child_name,))
            child_result = c.fetchone()
            if child_result:
                child_id = child_result[0]
            else:
                print(f"Error: No match found for child topic name '{child_name}'.")
                return

            # Insert the parent_id and child_id into topic_hierarchy
            c.execute("INSERT INTO topic_hierarchy (parent_id, child_id) VALUES (?, ?)", (parent_id, child_id))

        conn.commit()
        print("Topic hierarchy entries inserted successfully.")
    except Error as e:
        print(f"Error inserting topic hierarchy: {e}")
        conn.rollback()
    
def insert_hierarchical_topics_as_dag(conn, hier_topics: pd.DataFrame):
    """
    Convert hierarchical topics represented as a left-child right-sibling binary tree
    into a DAG and insert the relationships into the topic_hierarchy table, avoiding duplicates
    and self-links.

    Parameters:
    - conn: The database connection object.
    - hier_topics: A DataFrame containing hierarchical topics with columns for parent, child_left, and child_right.
    """
    try:
        c = conn.cursor()

        # Function to ensure a topic exists in the topics table and return its ID
        def ensure_topic_exists(name):
            c.execute("SELECT id FROM topics WHERE name = ?", (name,))
            result = c.fetchone()
            if result:
                return result[0]
            else:
                c.execute("INSERT INTO topics (name) VALUES (?)", (name,))
                return c.lastrowid

        # Function to check if a parent-child relationship already exists
        def relationship_exists(parent_id, child_id):
            c.execute("SELECT 1 FROM topic_hierarchy WHERE parent_topic_id = ? AND child_topic_id = ?", (parent_id, child_id))
            return c.fetchone() is not None

        # Process each row in the hierarchical topics DataFrame
        for _, row in hier_topics.iterrows():
            parent_name = row['Parent_Name']
            child_left_name = row['Child_Left_Name']
            child_right_name = row['Child_Right_Name']

            # Ensure all topics exist in the topics table and get their IDs
            parent_id = ensure_topic_exists(parent_name)
            child_left_id = ensure_topic_exists(child_left_name)
            child_right_id = ensure_topic_exists(child_right_name)

            # Insert parent-child relationships into topic_hierarchy, avoiding duplicates and self-links
            if parent_id != child_left_id and not relationship_exists(parent_id, child_left_id):
                c.execute("INSERT INTO topic_hierarchy (parent_topic_id, child_topic_id) VALUES (?, ?)", (parent_id, child_left_id))
            if parent_id != child_right_id and child_left_id != child_right_id and not relationship_exists(parent_id, child_right_id):
                c.execute("INSERT INTO topic_hierarchy (parent_topic_id, child_topic_id) VALUES (?, ?)", (parent_id, child_right_id))

        conn.commit()
        print("Hierarchical topics inserted into DAG successfully, avoiding duplicates and self-links.")
    except Error as e:
        print(f"Error inserting hierarchical topics as DAG: {e}")
        conn.rollback()