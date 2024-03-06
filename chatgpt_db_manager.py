import json
import sqlite3
from sqlite3 import Error
from functools import partial, reduce
import uuid
from typing import Dict, List, Tuple
import pandas as pd
import argparse
from db import connect_db, disconnect_db, execute_sql, create_database

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
            INSERT INTO chats (uuid, conversation_id, content_type, model, message, author, create_time, status, recipient, parent, is_first_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        '''

        for conversation in conversation_infos:
            execute_sql(conn, insert_conversation_sql, (conversation["id"], conversation["title"], conversation["create_time"], conversation["update_time"], conversation["is_archived"]), commit=True)

        for chat in all_chats:
            execute_sql(conn, insert_chat_sql, (chat["id"], chat["conversation_id"], chat["content_type"], chat["model"], json.dumps(chat["message"]), chat["author"], chat["create_time"], chat["status"], chat["recipient"], chat["parent"], chat["is_first_message"]), commit=True)

        disconnect_db(conn)
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
        SELECT c.uuid, c.conversation_id, c.content_type, c.model, c.message, c.author, c.create_time, c.status, c.recipient, c.parent, c.is_first_message, t.name AS label
        FROM chats c
        LEFT JOIN chat_topics ct ON c.id = ct.chat_uuid
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
        SELECT ct.chat_uuid, ct.topic_id, t.name AS label
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
    Fetch chat links from the database, including the topic label name for each chat link, the authors of the source and target chats,
    and the conversation ID of the source chat.
    
    Parameters:
    - conn: The database connection object.
    
    Returns:
    - A list of dictionaries, each representing a chat link with an additional 'label' field for the topic label name, 'source_author', 
    'target_author', 'source_conversation_id', and a UUIDv4 as 'id'.
    """
    try:
        cursor = conn.cursor()
        # Modified SQL query to join chat_links with topics to fetch the topic name as label, and also join with chats to get the authors
        # and include the conversation_id of the source chat
        query = """
        SELECT cl.source_chat_uuid, cl.target_chat_uuid, cl.topic_id, t.name AS label, sc.author AS source_author, 
        tc.author AS target_author, sc.conversation_id AS source_conversation_id
        FROM chat_links cl
        JOIN topics t ON cl.topic_id = t.id
        JOIN chats sc ON cl.source_chat_uuid = sc.uuid
        JOIN chats tc ON cl.target_chat_uuid = tc.uuid
        """
        cursor.execute(query)
        chat_links = cursor.fetchall()
        
        # Generate a UUIDv4 for each chat link and construct the result
        result = [
            {
                "id": str(uuid.uuid4()),
                "source_chat_uuid": chat_link[0],
                "target_chat_uuid": chat_link[1],
                "topic_id": chat_link[2],
                "label": chat_link[3],
                "source_author": chat_link[4],
                "target_author": chat_link[5],
                "conversation_id": chat_link[6]
            }
            for chat_link in chat_links
        ]
        
        return result
    except Error as e:
        print(f"Error fetching chat links with topics, authors, and conversation IDs: {e}")
        return []

def fetch_predicted_chat_links(conn):
    """
    Fetch predicted chat links from the database, including the score for each link.
    
    Parameters:
    - conn: The database connection object.
    
    Returns:
    - A list of dictionaries, each representing a predicted chat link with 'source_chat_uuid', 'target_chat_uuid', and 'score'.
    """
    try:
        cursor = conn.cursor()
        query = """
        SELECT source_chat_uuid, target_chat_uuid, score
        FROM predicted_chat_links
        """
        cursor.execute(query)
        predicted_chat_links = cursor.fetchall()
        
        # Construct the result
        result = [
            {
                "id": str(uuid.uuid4()),
                "source_chat_uuid": link[0],
                "target_chat_uuid": link[1],
                "score": link[2]
            }
            for link in predicted_chat_links
        ]
        
        return result
    except Error as e:
        print(f"Error fetching predicted chat links: {e}")
        return []
    
def fetch_conversation_id_for_chat(conn, chat_uuid):
    """
    Fetch the conversation_id for a given chat_uuid from the database.

    Parameters:
    - conn: The database connection object.
    - chat_uuid: The ID of the chat.

    Returns:
    - The conversation_id as a string, or None if not found.
    """
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT conversation_id FROM chats WHERE uuid = ?", (chat_uuid,))
        result = cursor.fetchone()
        if result:
            return result[0]
        return None
    except Error as e:
        print(f"Error fetching conversation_id for chat_uuid {chat_uuid}: {e}")
        return None
    
def fetch_conversations(conn):
    """
    Fetch conversations from the database using the fetch_table_data function.
    """
    query = "SELECT id, title, create_time, update_time, is_archived FROM conversations"
    return fetch_table_data(conn, query)

def fetch_chat(conn, chat_uuid) -> Dict:
    """
    Fetch chat data by chat ID from the database and return it as a dictionary.

    Parameters:
    - conn: The database connection object.
    - chat_uuid: The ID of the chat to fetch.

    Returns:
    - A dictionary containing the chat data, or None if not found.
    """
    try:
        c = conn.cursor()
        c.execute("SELECT * FROM chats WHERE uuid = ?", (chat_uuid,))
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
    chat_history = {}
    try:
        select_chats_sql = "SELECT * FROM chats"
        c = execute_sql(conn, select_chats_sql, return_cursor=True)
        rows = c.fetchall()
        if rows:
            columns = [col[0] for col in c.description]
            # Using a dictionary comprehension to create the desired structure
            # and map to aggregate the column data into lists
            chat_history = {column: [row[idx] for row in rows] for idx, column in enumerate(columns)}
    except Error as e:
        print(f"Error fetching all chat data: {e}")
    
    return chat_history

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
        c.execute("SELECT * FROM chats ORDER BY conversation_id, create_time")
        rows = c.fetchall()
        
        # If no rows are fetched, return an empty list
        if not rows:
            return []

        # Initialize a dictionary to hold lists of chat data for each conversation
        conversations = {}
        
        for row in rows:
            columns = [col[0] for col in c.description]
            chat_dict = dict(zip(columns, row))
            conversation_id = chat_dict['conversation_id']
                        
            # Initialize a dictionary for this conversation_id if it hasn't been already
            if conversation_id not in conversations:
                conversations[conversation_id] = {col: [] for col in columns}
            
            # Append data from the current row to the appropriate lists in the conversation's dictionary
            for col in columns:
                conversations[conversation_id][col].append(chat_dict[col])

        # Convert the conversations dictionary to a list of dictionaries
        return list(conversations.values())
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
            parent.uuid AS parent_uuid,
            child.uuid AS child_uuid,
            child.conversation_id,
            child.create_time,
            parent.message || ' ' || child.message AS message,
            parent.author AS parent_author,
            child.author AS child_author,
            parent.model AS parent_model,
            child.model AS child_model
        FROM
            chats AS child
            INNER JOIN chats AS parent ON child.parent = parent.uuid
        """
        c.execute(query)
        rows = c.fetchall()

        # If we have results, transform them into the desired dictionary format
        if rows:
            # Initialize keys with empty lists
            message_pairs = {
                "parent_uuid": [],
                "child_uuid": [],
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
                message_pairs["parent_uuid"].append(row[0])
                message_pairs["child_uuid"].append(row[1])
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

def insert_chat_topics(conn, chat_uuids: List[str], topic_names: List[str]):
    """
    Insert new chat topics into the chat_topics table. This function takes in a list of chat_uuids and topic_names,
    finds the matching topic_id for each topic_name, and inserts the chat_uuid and topic_id into the chat_topics table.
    If a topic_name does not exist in the topics table, it is inserted and its new topic_id is used.

    Parameters:
    - conn: The database connection object.
    - chat_uuids: A list of chat IDs.
    - topic_names: A list of topic names.

    Note: The function assumes that the lists chat_uuids and topic_names are of the same size.
    """
    if len(chat_uuids) != len(topic_names):
        print("Error: The lists of chat IDs and topic names must be the same size.")
        return

    try:
        c = conn.cursor()
        for chat_uuid, topic_name in zip(chat_uuids, topic_names):
            # Check if the topic exists and get its ID
            c.execute("SELECT id FROM topics WHERE name = ?", (topic_name,))
            topic_result = c.fetchone()

            if topic_result:
                topic_id = topic_result[0]
            else:
                # Insert the new topic if it doesn't exist
                c.execute("INSERT INTO topics (name) VALUES (?)", (topic_name,))
                topic_id = c.lastrowid  # Get the ID of the newly inserted topic

            # Insert the chat_uuid and topic_id into chat_topics
            c.execute("INSERT INTO chat_topics (chat_uuid, topic_id) VALUES (?, ?)", (chat_uuid, topic_id))

        conn.commit()
        print("Chat topics inserted successfully.")
    except Error as e:
        print(f"Error inserting chat topics: {e}")
        conn.rollback()

def insert_chat_links(conn, source_chat_uuids: List[str], target_chat_uuids: List[str], topic_names: List[str]):
    """
    Insert new chat links into the chat_links table. This function takes in lists of source_chat_uuids, target_chat_uuids,
    and topic_names, finds the matching topic_id for each topic_name, and inserts the source_chat_uuid, target_chat_uuid,
    and topic_id into the chat_links table. If a topic_name does not exist in the topics table, it is inserted and its
    new topic_id is used.

    Parameters:
    - conn: The database connection object.
    - source_chat_uuids: A list of source chat IDs.
    - target_chat_uuids: A list of target chat IDs.
    - topic_names: A list of topic names.

    Note: The function assumes that the lists source_chat_uuids, target_chat_uuids, and topic_names are of the same size.
    """
    if not (len(source_chat_uuids) == len(target_chat_uuids) == len(topic_names)):
        print("Error: The lists of source chat IDs, target chat IDs, and topic names must be the same size.")
        return

    try:
        c = conn.cursor()
        for source_chat_uuid, target_chat_uuid, topic_name in zip(source_chat_uuids, target_chat_uuids, topic_names):
            # Check if the topic exists and get its ID
            c.execute("SELECT id FROM topics WHERE name = ?", (topic_name,))
            topic_result = c.fetchone()

            if topic_result:
                topic_id = topic_result[0]
            else:
                # Insert the new topic if it doesn't exist
                c.execute("INSERT INTO topics (name) VALUES (?)", (topic_name,))
                topic_id = c.lastrowid  # Get the ID of the newly inserted topic

            # Insert the source_chat_uuid, target_chat_uuid, and topic_id into chat_links
            c.execute("INSERT INTO chat_links (source_chat_uuid, target_chat_uuid, topic_id) VALUES (?, ?, ?)", (source_chat_uuid, target_chat_uuid, topic_id))

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

def find_small_disjointed_conversation_links(conn):
    """
    Find all possible, but not valid, links between messages across disjointed conversations,
    considering only chats that are either the start of a chat or have no children.
    
    Parameters:
    - conn: The database connection object.
    
    Returns:
    - A list of RDF triples as strings, formatted as source_chat_uuid, source_author_to_target_author, target_chat_uuid.
    """
    try:
        c = conn.cursor()
        # Fetch chats that are the start of a conversation
        c.execute("SELECT uuid, conversation_id, author FROM chats WHERE is_first_message = 1")
        start_chats = c.fetchall()

        # Fetch chats that have no children
        c.execute("""
            SELECT c.uuid, c.conversation_id, c.author 
            FROM chats c
            LEFT JOIN chat_links cl ON c.uuid = cl.source_chat_uuid
            WHERE cl.source_chat_uuid IS NULL
        """)
        leaf_chats = c.fetchall()

        # Combine and deduplicate chats
        all_chats = list(set(start_chats + leaf_chats))

        # Group chats by conversation_id
        grouped_chats = {}
        for chat_uuid, conversation_id, author in all_chats:
            grouped_chats.setdefault(conversation_id, []).append((chat_uuid, author))

        # Generate all possible pairs of chats that are in different conversations
        rdf_triples = []
        for conv_id_1, chats_1 in grouped_chats.items():
            for conv_id_2, chats_2 in grouped_chats.items():
                if conv_id_1 != conv_id_2:
                    for chat1_id, chat1_author in chats_1:
                        for chat2_id, chat2_author in chats_2:
                            rdf_triple = f"{chat1_id} {chat1_author}_to_{chat2_author} {chat2_id}"
                            rdf_triples.append(rdf_triple)

        return rdf_triples
    except Error as e:
        print(f"Error finding disjoint conversation links: {e}")
        return []

def find_disjoint_conversation_links(conn):
    """
    Find all possible, but not valid, links between messages across disjointed conversations,
    excluding links between chats with the same author.
    
    Parameters:
    - conn: The database connection object.
    
    Returns:
    - A list of RDF triples as strings, formatted as source_chat_uuid, source_author_to_target_author, target_chat_uuid.
    """
    try:
        c = conn.cursor()
        # Fetch all chats with their conversation_id and author
        c.execute("SELECT uuid, conversation_id, author FROM chats")
        chats = c.fetchall()

        # Group chats by conversation_id
        grouped_chats = {}
        for chat in chats:
            chat_uuid, conversation_id, author = chat
            if conversation_id not in grouped_chats:
                grouped_chats[conversation_id] = []
            grouped_chats[conversation_id].append((chat_uuid, author))

        # Generate all possible pairs of chats that are in different conversations and have different authors
        rdf_triples = []
        conversation_ids = list(grouped_chats.keys())
        for i, conv_id_1 in enumerate(conversation_ids):
            for conv_id_2 in conversation_ids[i+1:]:
                for chat1 in grouped_chats[conv_id_1]:
                    for chat2 in grouped_chats[conv_id_2]:
                        if chat1[1] != chat2[1]:  # Check if authors are different
                            rdf_triple = f"{chat1[0]} {chat1[1]}_to_{chat2[1]} {chat2[0]}"
                            rdf_triples.append(rdf_triple)

        return rdf_triples
    except Error as e:
        print(f"Error finding disjoint conversation links: {e}")
        return []

def generate_rdf_triples(conn):
    """
    Generate RDF triples from chat links, chat topics, and topic links.
    
    Parameters:
    - conn: The database connection object.
    
    Returns:
    - A list of RDF triples as strings.
    """
    rdf_triples = []

    # Fetch chat links and generate triples
    chat_links = fetch_chat_links(conn)
    for link in chat_links:
        triple = f"{link['source_chat_uuid']} {link['label']} {link['target_chat_uuid']}"
        next_message_triple = f"{link['source_chat_uuid']} {link['source_author']}_to_{link['target_author']} {link['target_chat_uuid']}"
        rdf_triples.extend([triple, next_message_triple])

    # Fetch chat topics and generate triples
    chat_topics = fetch_chat_topics(conn)
    for link in chat_topics:
        triple = f"{link['label']} chat_type {link['chat_uuid']}"
        rdf_triples.append(triple)

    # Fetch topic links and generate triples
    topic_links = fetch_topic_links(conn)
    for link in topic_links:
        triple = f"{link['parent_label']} is_member_of {link['child_label']}"
        rdf_triples.append(triple)

    return rdf_triples

def insert_predicted_chat_links(conn, rdf_triples_with_scores):
    # Clear the existing data
    execute_sql(conn, "DELETE FROM predicted_chat_links", commit=True)
    
    # Insert new data
    insert_sql = '''
        INSERT INTO predicted_chat_links (source_chat_uuid, target_chat_uuid, score)
        VALUES (?, ?, ?);
    '''
    for triple in rdf_triples_with_scores:
        source_chat_uuid, label, target_chat_uuid, score = triple  # Directly unpack the tuple
        execute_sql(conn, insert_sql, (source_chat_uuid, target_chat_uuid, float(score)), commit=True)

    print("Predicted chat links updated successfully.")

def find_disjoint_conversation_links_for_specific_conv(conn, specific_conv_id):
    """
    Find all possible, but not valid, links between messages of a specific conversation
    and messages across all other disjointed conversations, excluding links between chats
    with the same author.
    
    Parameters:
    - conn: The database connection object.
    - specific_conv_id: The ID of the specific conversation to compare against all others.
    
    Returns:
    - A list of RDF triples as strings, formatted as source_chat_uuid, source_author_to_target_author, target_chat_uuid.
    """
    try:
        c = conn.cursor()
        # Fetch all chats with their conversation_id and author
        c.execute("SELECT uuid, conversation_id, author FROM chats")
        chats = c.fetchall()

        # Group chats by conversation_id
        grouped_chats = {}
        for chat in chats:
            chat_uuid, conversation_id, author = chat
            grouped_chats.setdefault(conversation_id, []).append((chat_uuid, author))

        # Ensure the specific conversation exists
        if specific_conv_id not in grouped_chats:
            print(f"No conversation found with ID: {specific_conv_id}")
            return []

        # Extract chats for the specific conversation
        specific_conv_chats = grouped_chats[specific_conv_id]

        # Generate all possible pairs of chats that are in different conversations and have different authors
        rdf_triples = []
        for conv_id, chats in grouped_chats.items():
            if conv_id != specific_conv_id:  # Exclude the specific conversation itself
                for chat1 in specific_conv_chats:
                    for chat2 in chats:
                        if chat1[1] != chat2[1]:  # Check if authors are different
                            rdf_triple = f"{chat1[0]} {chat1[1]}_to_{chat2[1]} {chat2[0]}"
                            rdf_triples.append(rdf_triple)

        return rdf_triples
    except Error as e:
        print(f"Error finding disjoint conversation links for specific conversation {specific_conv_id}: {e}")
        return []

def generate_rdf_subcommand(args):
    conn = connect_db(args.db_file)
    if conn is not None:
        rdf_triples = generate_rdf_triples(conn)
        if args.output:
            with open(args.output, "w") as file:
                for triple in rdf_triples:
                    file.write(triple + "\n")
            print(f"RDF triples have been written to {args.output}")
        else:
            for triple in rdf_triples[:5]:  # Print the first 5 triples for demonstration
                print(triple)
    else:
        print("Failed to connect to the database.")

def find_disjoint_subcommand(args):
    conn = connect_db(args.db_file)
    if conn is not None:
        rdf_triples = find_disjoint_conversation_links(conn)
        if args.output:
            with open(args.output, "w") as file:
                for triple in rdf_triples:
                    file.write(triple + "\n")
            print(f"Disjoint conversation links have been written to {args.output}")
        else:
            for triple in rdf_triples[:5]:  # Print the first 5 triples for demonstration
                print(triple)
    else:
        print("Failed to connect to the database.")

def insert_predicted_chat_links_subcommand(args):
    conn = connect_db(args.db_file)
    if conn is not None:
        # Read the predicted links from the text file
        with open(args.links_file, 'r') as file:
            lines = file.readlines()
            # Parse the space-delimited data
            rdf_triples_with_scores = [line.strip().split() for line in lines]
            print(rdf_triples_with_scores)
            # Call the insert function
            insert_predicted_chat_links(conn, rdf_triples_with_scores)
        print("Predicted chat links inserted successfully.")
    else:
        print("Failed to connect to the database.")

def fetch_conversation_id_subcommand(args):
    conn = connect_db(args.db_file)
    if conn is not None:
        conversation_id = fetch_conversation_id_for_chat(conn, args.chat_uuid)
        if conversation_id:
            print(f"Conversation ID for chat ID {args.chat_uuid}: {conversation_id}")
        else:
            print(f"No conversation found for chat ID {args.chat_uuid}")
    else:
        print("Failed to connect to the database.")

def find_disjoint_conversation_links_for_specific_conv_subcommand(args):
    conn = connect_db(args.db_file)
    if conn is not None:
        rdf_triples = find_disjoint_conversation_links_for_specific_conv(conn, args.specific_conv_id)
        if args.output:
            with open(args.output, "w") as file:
                for triple in rdf_triples:
                    file.write(triple + "\n")
            print(f"Disjoint conversation links for specific conversation have been written to {args.output}")
        else:
            for triple in rdf_triples[:5]:  # Print the first 5 triples for demonstration
                print(triple)
    else:
        print("Failed to connect to the database.")

def create_database_subcommand(args):
    """CLI command to create the database."""
    create_database(args.db_file)
    print(f"Database created at {args.db_file}")

def main():
    parser = argparse.ArgumentParser(description="Chat database management and RDF triple generation.")
    subparsers = parser.add_subparsers(help='commands')

    create_db_parser = subparsers.add_parser('create_db', help='Create the database and tables.')
    create_db_parser.add_argument('db_file', type=str, help='Path to the SQLite database file.')
    create_db_parser.set_defaults(func=create_database_subcommand)

    # Generate RDF triples command
    rdf_parser = subparsers.add_parser('generate_rdf', help='Generate RDF triples from chat database.')
    rdf_parser.add_argument("db_file", help="Path to the SQLite database file.")
    rdf_parser.add_argument("-o", "--output", help="Path to the output file for RDF triples.", default=None)
    rdf_parser.set_defaults(func=generate_rdf_subcommand)

    # Find disjoint conversation links command
    disjoint_parser = subparsers.add_parser('possible_links', help='Find disjoint conversation links and output RDF triples.')
    disjoint_parser.add_argument("db_file", help="Path to the SQLite database file.")
    disjoint_parser.add_argument("-o", "--output", help="Path to the output file for RDF triples.", default=None)
    disjoint_parser.set_defaults(func=find_disjoint_subcommand)

    insert_links_parser = subparsers.add_parser('insert_predicted_chat_links', help='Insert predicted chat links into the database.')
    insert_links_parser.add_argument("db_file", help="Path to the SQLite database file.")
    insert_links_parser.add_argument("links_file", help="Path to the text file containing predicted links.")
    insert_links_parser.set_defaults(func=insert_predicted_chat_links_subcommand)

    fetch_conversation_id_parser = subparsers.add_parser('fetch_conversation_id', help='Fetch the conversation_id for a given chat_uuid.')
    fetch_conversation_id_parser.add_argument("db_file", help="Path to the SQLite database file.")
    fetch_conversation_id_parser.add_argument("chat_uuid", help="The chat_uuid to fetch the conversation_id for.")
    fetch_conversation_id_parser.set_defaults(func=fetch_conversation_id_subcommand)

    specific_links_parser = subparsers.add_parser('find_specific_links', help='Find disjoint conversation links for a specific conversation.')
    specific_links_parser.add_argument("db_file", help="Path to the SQLite database file.")
    specific_links_parser.add_argument("specific_conv_id", help="The specific conversation ID to compare against all others.")
    specific_links_parser.add_argument("-o", "--output", help="Path to the output file for RDF triples.", default=None)
    specific_links_parser.set_defaults(func=find_disjoint_conversation_links_for_specific_conv_subcommand)

    args = parser.parse_args()
    if hasattr(args, 'func'):
        args.func(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()