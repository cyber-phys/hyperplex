import json
import sqlite3
from sqlite3 import Error

def create_database(db_file):
    """Create a SQLite database and tables for conversations and chats."""
    try:
        # Connect to the SQLite database; it creates the file if it does not exist
        conn = sqlite3.connect(db_file)
        c = conn.cursor()

        # Modify conversations table to be consistent with existing conventions
        c.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT UNIQUE PRIMARY KEY,
                title TEXT,
                create_time TEXT,
                update_time TEXT,
                is_archived BOOLEAN
            );
        ''')

        # Modify chats table to be consistent with existing conventions
        c.execute('''
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
                is_first_message BOOLEAN
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            );
        ''')

        # Commit the changes and close the connection
        conn.commit()
        conn.close()
        print("Database and tables created successfully.")
    except Error as e:
        print(f"Error creating database: {e}")

def parse_json(file_path):
    with open(file_path, 'r') as f:
        data = json.load(f)

    conversation_infos = []
    all_chats = []
    all_metadata_values = set()

    for conversation in data:
        conversation_info = {
            "id": conversation["id"],
            "title": conversation["title"],
            "create_time": conversation["create_time"],
            "update_time": conversation["update_time"],
            "conversation_id": conversation["conversation_id"],
        }

        chats = []
        metadata_values = set()

        first_entry_id = next(iter(conversation["mapping"]))

        for chat_id, chat_data in conversation["mapping"].items():
            is_first_message = (chat_id == first_entry_id)
            if chat_data["message"] is not None:
                message_text = []
                model = "unknown"
                content_type = chat_data["message"]["content"]["content_type"]
                role = chat_data["message"]["author"]["role"]

                if role == "user":
                    model = "user"
                elif role == "assistant":
                    if "model_slug" not in chat_data["message"]["metadata"]:
                        model = "gpt-3.5"
                    else:
                        model = chat_data["message"]["metadata"]["model_slug"]
                elif role == "tool":
                    model = chat_data["message"]["metadata"]["model_slug"]
                
 
                # Check if the content type is 'text' and extract parts if they exist
                if content_type == "text" and "parts" in chat_data["message"]["content"]:
                    message_parts = chat_data["message"]["content"]["parts"]
                    message_text = [part for part in message_parts if isinstance(part, str)]
                # Handle 'multimodal_text' by extracting the string directly from parts
                elif content_type == "multimodal_text":
                    message_parts = chat_data["message"]["content"]["parts"]
                    message_text = [part for part in message_parts if isinstance(part, str)]
                # For 'code' or other types with direct text content, extract the text directly
                elif "text" in chat_data["message"]["content"]:
                    message_text = [chat_data["message"]["content"]["text"]]
                # Handle 'tether_browsing_display' by extracting the result directly
                elif role == "tool" and "result" in chat_data["message"]["content"]:
                    message_text = [chat_data["message"]["content"]["result"]]
                else:
                    print(chat_data)

                # Append the chat data with the extracted message
                if message_text:  # Ensure there's text to add
                    chats.append({
                        "id": chat_data["id"],
                        "content_type": content_type,
                        "model": model,
                        "message": message_text,
                        "author": chat_data["message"]["author"]["role"],
                        "create_time": chat_data["message"]["create_time"],
                        "status": chat_data["message"]["status"],
                        "recipient": chat_data["message"]["recipient"],
                        "parent": chat_data["parent"],
                        "children": chat_data["children"],
                        "conversation_id": conversation["id"],
                        "is_first_message": is_first_message
                    })

        conversation_infos.append(conversation_info)
        all_chats.extend(chats)
        all_metadata_values.update(metadata_values)

    return conversation_infos, all_chats, all_metadata_values

# Use the function
conversation_info, chats, metadata_values = parse_json('../chatgpt_export_12_29_24/conversations.json')

chats_with_multiple_children = [chat for chat in chats if len(chat["children"]) > 1]
print(chats_with_multiple_children[0]["children"])

