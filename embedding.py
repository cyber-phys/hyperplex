import sqlite3
import argparse
from typing import Callable
from uuid import uuid4
import concurrent.futures
from sentence_transformers import SentenceTransformer, util
import functools
from nltk.tokenize import sent_tokenize
import nltk
import torch
import numpy
import time
# from bertopic import BERTopic
# from hdbscan import HDBSCAN
from db import connect_db, execute_sql, create_database
nltk.download('punkt')

def get_user_labels(db_path: str) -> list:
    """
    Retrieve all user labels from the database.

    Args:
        db_path (str): The path to the SQLite database.

    Returns:
        list: A list of user labels.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT label FROM labels WHERE is_user_label = 1")
    labels = cursor.fetchall()
    conn.close()
    return [label[0] for label in labels]

def fetch_entries_with_user_labels_and_embeddings_chunk(db_path: str, model_uuid: str, chunk_size: int, chunk_number: int) -> tuple:
    """
    Fetch a specific chunk of entries from the embeddings table in the database along with their user labels,
    bert_label_ids, and embeddings, in a memory-efficient manner.

    Args:
        db_path (str): The path to the SQLite database.
        model_uuid (str): The UUID of the model to match embeddings.
        chunk_size (int): The size of each chunk to be fetched.
        chunk_number (int): The specific chunk number to return.

    Returns:
        tuple: A tuple containing a list of tuples for each entry in the specified chunk, where each entry tuple contains:
               - text_segment (str): The text segment corresponding to the embedding's character positions.
               - text_uuid (str): The UUID of the associated law entry.
               - label (str): The user label name associated with the embedding or an empty string if none.
               - bert_label_id (int): The associated bert_label_id or -1 if none.
               - embedding (numpy.ndarray): The embedding blob converted to a NumPy array.
               The second element of the tuple is the total number of chunks available.

    Raises:
        ValueError: If the requested chunk_number is out of range.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT
            (SELECT COUNT(*)
            FROM embeddings e
            INNER JOIN text_label_link ult ON e.text_uuid = ult.text_uuid
            WHERE e.model_uuid = ? AND (e.char_start <= ult.char_end AND e.char_end >= ult.char_start)
            ) +
            (SELECT COUNT(DISTINCT e.uuid)
            FROM embeddings e
            WHERE e.model_uuid = ? AND NOT EXISTS (
                SELECT 1
                FROM text_label_link ult
                WHERE e.text_uuid = ult.text_uuid AND (e.char_start <= ult.char_end AND e.char_end >= ult.char_start)
            )
        ) AS total_count
    """, (model_uuid, model_uuid))
    total_entries = cursor.fetchone()[0]
    total_chunks = (total_entries + chunk_size - 1) // chunk_size
    
    if chunk_number < 1 or chunk_number > total_chunks:
        conn.close()
        raise ValueError(f"Requested chunk number {chunk_number} is out of range. Total available chunks: {total_chunks}.")

    offset = (chunk_number - 1) * chunk_size

    select_statement = """
    SELECT substr(le.text, e.char_start + 1, e.char_end - e.char_start) as text_segment, 
           e.text_uuid, 
           COALESCE(l.label, '') as label, 
           COALESCE(l.bert_id, -1) as bert_label_id, 
           e.embedding
    FROM embeddings e
    INNER JOIN law_entries le ON e.text_uuid = le.uuid
    LEFT JOIN text_label_link ult ON e.text_uuid = ult.text_uuid AND e.char_start <= ult.char_end AND e.char_end >= ult.char_start
    LEFT JOIN labels l ON ult.label_uuid = l.label_uuid
    WHERE e.model_uuid = ?
    GROUP BY e.uuid, l.label
    ORDER BY e.uuid
    LIMIT ? OFFSET ?;
    """
    
    cursor.execute(select_statement, (model_uuid, chunk_size, offset))
    entries = cursor.fetchall()
    conn.close()
    
    if not entries:
        return ([], [], [], []), [], total_chunks
    
    texts, uuids, labels, bert_label_ids, embeddings_list = zip(*[(entry[0], entry[1], entry[2], entry[3], numpy.frombuffer(entry[4], dtype=numpy.float32) if entry[4] else numpy.array([])) for entry in entries])
    embeddings = numpy.stack(embeddings_list) if embeddings_list[0].size > 0 else numpy.array([])
    
    return (texts, labels, uuids, bert_label_ids, embeddings), total_chunks

def fetch_entries(db_path):
    """
    Fetch all entries from the law_entries table in the database.

    Args:
        db_path (str): The path to the SQLite database.

    Returns:
        tuple: Two lists, one containing the texts and the other containing the uuids of the law entries.
    """
    # Connect to the SQLite3 database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # SQL statement to select all texts and uuids
    select_statement = "SELECT text, uuid FROM law_entries;"
    
    # Execute the SQL statement
    cursor.execute(select_statement)
    
    # Fetch all rows
    entries = cursor.fetchall()
    
    # Close the connection
    conn.close()
    
    # Unpack texts and uuids into separate lists
    texts, uuids = zip(*entries) if entries else ([], [])
    
    return texts, uuids

def fetch_entries_with_embeddings(db_path: str) -> tuple:
    """
    Fetch all entries from the law_entries table in the database along with their embeddings.

    Args:
        db_path (str): The path to the SQLite database.

    Returns:
        tuple: Three lists, one containing the texts, one containing the uuids of the law entries, and one containing the embeddings.
    """
    # Connect to the SQLite3 database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # SQL statement to join law_entries and embeddings tables and select texts, uuids, and embeddings
    select_statement = """
    SELECT le.text, le.uuid, e.embedding
    FROM law_entries le
    INNER JOIN embeddings e ON le.uuid = e.text_uuid;
    """
    
    # Execute the SQL statement
    cursor.execute(select_statement)
    
    # Fetch all rows
    entries = cursor.fetchall()
    
    # Close the connection
    conn.close()
    
    # If there are no entries, return empty lists
    if not entries:
        return ([], [], [])
    
    # Unpack texts, uuids, and embeddings into separate lists
    texts, uuids, embeddings_list = zip(*[(entry[0], entry[1], numpy.frombuffer(entry[2], dtype=numpy.float32)) for entry in entries])
    
    # Convert list of embeddings to a single NumPy array
    embeddings = numpy.stack(embeddings_list)
    
    return texts, uuids, embeddings

def fetch_entries_with_embeddings_chunked(db_path: str, chunk_size: int) -> list:
    """
    Fetch all entries from the law_entries table in the database along with their embeddings,
    and return them in chunks of a specified size.

    Args:
        db_path (str): The path to the SQLite database.
        chunk_size (int): The size of each chunk.

    Returns:
        list: A list of tuples, each tuple containing three lists (texts, uuids, embeddings) for a chunk.
    """
    # Connect to the SQLite3 database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # SQL statement to join law_entries and embeddings tables and select texts, uuids, and embeddings
    select_statement = """
    SELECT le.text, le.uuid, e.embedding
    FROM law_entries le
    INNER JOIN embeddings e ON le.uuid = e.text_uuid;
    """
    
    # Execute the SQL statement
    cursor.execute(select_statement)
    
    # Fetch all rows
    entries = cursor.fetchall()
    
    # Close the connection
    conn.close()
    
    # If there are no entries, return an empty list
    if not entries:
        return []
    
    # Unpack texts, uuids, and embeddings into separate lists
    texts, uuids, embeddings_list = zip(*[(entry[0], entry[1], numpy.frombuffer(entry[2], dtype=numpy.float32)) for entry in entries])
    
    # Initialize lists to hold chunks
    chunked_texts = [texts[i:i + chunk_size] for i in range(0, len(texts), chunk_size)]
    chunked_uuids = [uuids[i:i + chunk_size] for i in range(0, len(uuids), chunk_size)]
    chunked_embeddings = [embeddings_list[i:i + chunk_size] for i in range(0, len(embeddings_list), chunk_size)]
    
    # Convert list of embeddings in each chunk to a single NumPy array
    chunked_embeddings = [numpy.stack(chunk) for chunk in chunked_embeddings]
    
    # Zip the chunked lists together to form tuples for each chunk
    chunked_entries = list(zip(chunked_texts, chunked_uuids, chunked_embeddings))
    
    return chunked_entries

def fetch_entries_with_embeddings_specific_chunk(db_path: str, model_uuid: str, chunk_size: int, chunk_number: int) -> tuple:
    """
    Fetch a specific chunk of entries from the embeddings table in the database along with their text segments from law_entries,
    in a memory-efficient manner by only loading the required chunk of data.

    Args:
        db_path (str): The path to the SQLite database.
        model_uuid (str): The UUID of the model to match embeddings.
        chunk_size (int): The size of each chunk.
        chunk_number (int): The specific chunk number to return.

    Returns:
        tuple: A tuple containing four lists (text segments, uuids of the law entries, uuids of the embeddings, embeddings) for the specified chunk and the total number of chunks.
    """
    # Connect to the SQLite3 database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # First, get the total number of entries in embeddings for the given model_uuid to calculate the total number of chunks
    cursor.execute("SELECT COUNT(*) FROM embeddings WHERE model_uuid = ?", (model_uuid,))
    total_entries = cursor.fetchone()[0]
    total_chunks = (total_entries + chunk_size - 1) // chunk_size
    
    # Check if the requested chunk number is within the range of available chunks
    if chunk_number < 1 or chunk_number > total_chunks:
        conn.close()
        raise ValueError(f"Requested chunk number {chunk_number} is out of range. Total available chunks: {total_chunks}.")

    # Calculate the offset for the SQL query
    offset = (chunk_number - 1) * chunk_size

    # Modify the SQL query to fetch only the specific chunk of data from embeddings and the corresponding text segment from law_entries
    select_statement = """
    SELECT le.text, e.text_uuid, e.uuid, e.char_start, e.char_end, e.embedding
    FROM embeddings e
    INNER JOIN law_entries le ON e.text_uuid = le.uuid
    WHERE e.model_uuid = ?
    LIMIT ? OFFSET ?;
    """
    
    # Execute the SQL statement with model_uuid, chunk_size, and offset
    cursor.execute(select_statement, (model_uuid, chunk_size, offset))
    
    # Fetch the rows for the specific chunk
    entries = cursor.fetchall()
    
    # Close the connection
    conn.close()
    
    # If there are no entries, return empty lists and 0 as the number of chunks
    if not entries:
        return ([], [], [], []), total_chunks
    
    # Unpack text segments, uuids, embedding uuids, and embeddings into separate lists
    text_segments = [entry[0][entry[3]:entry[4]] for entry in entries]  # Extract text segment using char_start and char_end
    text_uuids = [entry[1] for entry in entries]
    embedding_uuids = [entry[2] for entry in entries]
    embeddings_list = [numpy.frombuffer(entry[5], dtype=numpy.float32) for entry in entries]
    
    # Convert the list of embeddings to a single NumPy array
    embeddings = numpy.stack(embeddings_list)
    
    return (text_segments, text_uuids, embedding_uuids, embeddings), total_chunks

# def fetch_entries_with_embeddings_specific_chunk(db_path: str, chunk_size: int, chunk_number: int) -> tuple:
#     """
#     Fetch a specific chunk of entries from the law_entries table in the database along with their embeddings,
#     in a memory-efficient manner by only loading the required chunk of data.

#     Args:
#         db_path (str): The path to the SQLite database.
#         chunk_size (int): The size of each chunk.
#         chunk_number (int): The specific chunk number to return.

#     Returns:
#         tuple: A tuple containing three lists (texts, uuids, embeddings) for the specified chunk and the total number of chunks.
#     """
#     # Connect to the SQLite3 database
#     conn = sqlite3.connect(db_path)
#     cursor = conn.cursor()
    
#     # First, get the total number of entries to calculate the total number of chunks
#     cursor.execute("SELECT COUNT(*) FROM law_entries")
#     total_entries = cursor.fetchone()[0]
#     total_chunks = (total_entries + chunk_size - 1) // chunk_size
    
#     # Check if the requested chunk number is within the range of available chunks
#     if chunk_number < 1 or chunk_number > total_chunks:
#         print(f"Requested chunk number {chunk_number} is out of range. Total available chunks: {total_chunks}.")
#         raise ValueError(f"Requested chunk number {chunk_number} is out of range. Total available chunks: {total_chunks}.")

#     # Calculate the offset for the SQL query
#     offset = (chunk_number - 1) * chunk_size

#     # Modify the SQL query to fetch only the specific chunk of data
#     select_statement = """
#     SELECT le.text, le.uuid, e.embedding
#     FROM law_entries le
#     INNER JOIN embeddings e ON le.uuid = e.text_uuid
#     LIMIT ? OFFSET ?;
#     """
    
#     # Execute the SQL statement with chunk_size and offset
#     cursor.execute(select_statement, (chunk_size, offset))
    
#     # Fetch the rows for the specific chunk
#     entries = cursor.fetchall()
    
#     # Close the connection
#     conn.close()
    
#     # If there are no entries, return empty lists and 0 as the number of chunks
#     if not entries:
#         return ([], [], []), total_chunks
    
#     # Unpack texts, uuids, and embeddings into separate lists
#     texts, uuids, embeddings_list = zip(*[(entry[0], entry[1], numpy.frombuffer(entry[2], dtype=numpy.float32)) for entry in entries])
    
#     # Convert the list of embeddings to a single NumPy array
#     embeddings = numpy.stack(embeddings_list)
    
#     return (texts, uuids, embeddings), total_chunks

def store_cluster_link_entries_bulk(db_path: str, entries: list) -> None:
    """
    Store multiple entries in the cluster_label_link table using bulk insert.
    Roll back if any error occurs during the insert.

    Args:
        db_path (str): The path to the SQLite database.
        entries (list): A list of tuples containing the label_name, text_uuid, and embedding_uuid for each entry.
    """
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        # Prepare the bulk insert statement for labels and cluster_label_link
        insert_label_statement = """
            INSERT INTO labels (label_uuid, label, creation_time)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(label) DO NOTHING
        """
        insert_link_statement = """
            INSERT INTO cluster_label_link (label_uuid, text_uuid, creation_time)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(label_uuid, text_uuid) DO NOTHING
        """

        try:
            # Begin a transaction
            conn.execute('BEGIN TRANSACTION;')

            # Insert labels and links in bulk
            label_uuids = {}
            for label_name, text_uuid in entries:
                if label_name not in label_uuids:
                    label_uuid = str(uuid4())
                    label_uuids[label_name] = label_uuid
                    cursor.execute(insert_label_statement, (label_uuid, label_name))

                cursor.execute(insert_link_statement, (label_uuids[label_name], text_uuid))

            # Commit the transaction
            conn.commit()
        except sqlite3.Error as e:
            # Roll back any changes if an error occurs
            conn.rollback()
            raise e

def store_cluster_link_entry(db_path: str, text: str, label_name: str, text_uuid: str, embedding_uuid: str, verbose: bool = False) -> None:
    """
    Store an entry in the cluster_label_link table by finding the corresponding label_uuid and text_uuid.
    If the label does not exist, it is added to the labels table.
    Avoid inserting a duplicate entry if a link already exists.

    Args:
        db_path (str): The path to the SQLite database.
        text (str): The text of the law entry.
        label_name (str): The name of the label.

    Returns:
        None
    """
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        # Find or create the label_uuid for the given label_name
        cursor.execute("SELECT label_uuid FROM labels WHERE label = ?", (label_name,))
        label_result = cursor.fetchone()

        if label_result:
            label_uuid = label_result[0]
        else:
            label_uuid = str(uuid4())
            cursor.execute("""
                INSERT INTO labels (label_uuid, label, creation_time)
                VALUES (?, ?, datetime('now'))
            """, (label_uuid, label_name))

        # # Find the text_uuid for the given text
        # cursor.execute("SELECT uuid FROM law_entries WHERE text = ?", (text,))
        # entry_result = cursor.fetchone()

        # if not entry_result:
        #     raise ValueError(f"No law entry found with the given text.")

        # text_uuid = entry_result[0]

        # Check if the link already exists
        cursor.execute("""
            SELECT * FROM cluster_label_link
            WHERE label_uuid = ? AND text_uuid = ?
        """, (label_uuid, text_uuid))
        link_exists = cursor.fetchone()

        if not link_exists:
            # Insert into cluster_label_link table
            cursor.execute("""
                INSERT INTO cluster_label_link (label_uuid, text_uuid, creation_time)
                VALUES (?, ?, datetime('now'))
            """, (label_uuid, text_uuid))
        if link_exists and verbose:
            print(f"label link exists: {text_uuid} --> {label_name}")

def cluster_entries(db_path: str, model_name: str, min_community_size: int = 25, threshold: float = 0.75):
    """
    Cluster law entries based on their embeddings and print out the clusters.

    Args:
        db_path (str): The path to the SQLite database.
        model_name (str): The name of the model to use for computing embeddings.
        min_community_size (int): Minimum number of entries to form a cluster.
        threshold (float): Cosine similarity threshold for considering entries as similar.
    """
    # Connect to the database and retrieve embeddings
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT text_uuid, embedding FROM embeddings")
    entries = cursor.fetchall()
    cursor.execute("SELECT model FROM nlp_model WHERE label = ?", (model_name,))
    model_name_row = cursor.fetchone()
    conn.close()

    model_name = model_name_row[0]
    model = SentenceTransformer(model_name, device="cpu")

    if not model_name_row:
        print(f"No model found with label '{model_name}'.")
        return
        
    # Extract embeddings and convert them to tensors
    text_uuids = [entry[0] for entry in entries]
    embeddings = [torch.Tensor(numpy.frombuffer(entry[1], dtype=numpy.float32)) for entry in entries]
    embeddings_tensor = torch.stack(embeddings)

    print("Start clustering")
    start_time = time.time()

    # Perform clustering
    clusters = util.community_detection(embeddings_tensor, min_community_size=min_community_size, threshold=threshold)

    print("Clustering done after {:.2f} sec".format(time.time() - start_time))

    # Print out the clusters
    for i, cluster in enumerate(clusters):
        print("\nCluster {}, #{} Elements ".format(i + 1, len(cluster)))
        for entry_id in cluster:
            print("\tUUID: ", text_uuids[entry_id])
    
    return

def insert_user_label_text(db_path: str, label_name: str, text_uuid: str, char_start: int, char_end: int) -> None:
    """
    Insert a new label text for a user label. If the label does not exist, create a new one.

    Args:
        db_path (str): The path to the SQLite database.
        label_name (str): The name of the label.
        text_uuid (str): The UUID of the text to label.
        char_start (int): The starting character position of the label in the text.
        char_end (int): The ending character position of the label in the text.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if the label exists; if not, create it
    cursor.execute("SELECT label_uuid FROM labels WHERE label = ?", (label_name,))
    label_result = cursor.fetchone()

    if label_result:
        label_uuid = label_result[0]
    else:
        # If the label does not exist or is not a user label, create a new user label with the current datetime
        label_uuid = str(uuid4())
        cursor.execute("""
            INSERT INTO labels (label_uuid, label, is_user_label, creation_time)
            VALUES (?, ?, 1, datetime('now'))
        """, (label_uuid, label_name))
    
    # Insert the new label text into text_label_link table
    cursor.execute("""
        INSERT INTO text_label_link (label_uuid, text_uuid, creation_time, char_start, char_end)
        VALUES (?, ?, datetime('now'), ?, ?)
    """, (label_uuid, text_uuid, char_start, char_end))

    conn.commit()
    conn.close()

def insert_label(db_path, label_text, color='blue'):
    """
    Insert a new label into the labels table if it doesn't already exist.

    Args:
        db_path (str): The path to the SQLite database.
        label_text (str): The text of the label to insert.
        color (str, optional): The color associated with the label.

    Returns:
        str: The UUID of the inserted or existing label.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if the label already exists
    cursor.execute("SELECT label_uuid FROM labels WHERE label = ?", (label_text,))
    existing_label = cursor.fetchone()

    if existing_label:
        label_uuid = existing_label[0]  # Use the existing label's UUID
    else:
        # If the label does not exist, insert a new one
        label_uuid = str(uuid4())
        cursor.execute("""
            INSERT INTO labels (label_uuid, label, creation_time, color)
            VALUES (?, ?, datetime('now'), ?)
        """, (label_uuid, label_text, color))
        conn.commit()

    conn.close()
    return label_uuid

def list_labels(db_path):
    """
    List all labels in the labels table.

    Args:
        conn: The database connection object.

    Returns:
        list: A list of tuples containing label details.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT label_uuid, label, creation_time, color FROM labels WHERE is_user_label = 1")
    return cursor.fetchall()

def fetch_law_entries(conn, chunking_method, chunking_size, batch_size=1000):
    """
    Generator function to yield batches of law entries from the database, chunked according to the specified method and size,
    along with the character start and end positions of each chunk.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT uuid, text FROM law_entries")
    while True:
        entries = cursor.fetchmany(batch_size)
        if not entries:
            break
        chunked_entries = []
        for entry in entries:
            text_uuid, text = entry
            char_start = 0
            if chunking_method == 'sentence':
                sentences = sent_tokenize(text)
                for i in range(0, len(sentences), chunking_size):
                    chunk = ' '.join(sentences[i:i+chunking_size])
                    char_end = char_start + len(chunk)
                    chunked_entries.append((text_uuid, chunk, char_start, char_end))
                    char_start = char_end + 1  # +1 for the space after each chunk
            elif chunking_method == 'word':
                words = text.split()
                for i in range(0, len(words), chunking_size):
                    chunk = ' '.join(words[i:i+chunking_size])
                    char_end = char_start + len(chunk)
                    chunked_entries.append((text_uuid, chunk, char_start, char_end))
                    char_start = char_end + 1  # +1 for the space after each chunk
            elif chunking_method == 'char':
                for i in range(0, len(text), chunking_size):
                    chunk = text[i:i+chunking_size]
                    char_end = char_start + len(chunk)
                    chunked_entries.append((text_uuid, chunk, char_start, char_end))
                    char_start = char_end
        yield chunked_entries

def compute_embeddings(model_name, texts):
    """
    Pure function to compute embeddings for a list of texts using the specified model.
    """
    model = SentenceTransformer(model_name, device="cpu")
    embeddings = model.encode(texts, convert_to_tensor=False)
    return embeddings

def store_embeddings(conn, model_uuid, entries_with_positions):
    """
    Function to store embeddings in the database along with their character start and end positions.
    """
    cursor = conn.cursor()
    for text_uuid, char_start, char_end, embedding in entries_with_positions:
        cursor.execute("""
            INSERT INTO embeddings (model_uuid, text_uuid, creation_time, char_start, char_end, embedding)
            VALUES (?, ?, datetime('now'), ?, ?, ?)
        """, (model_uuid, text_uuid, char_start, char_end, embedding.tobytes()))

def process_batch(model_name, model_uuid, batch, db_path):
    """
    Function to process a batch of entries, compute embeddings, and store them in the database.
    """
    # Unpack the batch to separate the texts and their corresponding char positions
    text_uuids, texts, char_starts, char_ends = zip(*batch)
    embeddings = compute_embeddings(model_name, texts)
    conn = sqlite3.connect(db_path)
    # Combine the entries and their char positions with the computed embeddings
    entries_with_positions = zip(text_uuids, char_starts, char_ends, embeddings)
    store_embeddings(conn, model_uuid, entries_with_positions)
    conn.commit()
    conn.close()

def create_embedding(db_path, label, model_name, chunking_method, chunking_size, verbose=False):
    """
    Creates new embeddings with the specified model, chunking method, and chunking size.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if an entry with the same label already exists
    cursor.execute("SELECT uuid FROM nlp_model WHERE label = ?", (label,))
    result = cursor.fetchone()
    if result:
        print(f"Error: An entry with the label '{label}' already exists.")
        conn.close()
        return

    # Insert a new entry into the nlp_model table
    model_uuid = str(uuid4())
    cursor.execute("""
        INSERT INTO nlp_model (uuid, model, label, chunking_method, chunking_size)
        VALUES (?, ?, ?, ?, ?)
    """, (model_uuid, model_name, label, chunking_method, chunking_size))
    conn.commit()

    # Fetch and process entries in batches
    batches = fetch_law_entries(conn, chunking_method, chunking_size)
    with concurrent.futures.ThreadPoolExecutor() as executor:
        # Use functools.partial to create a new function with some parameters of process_batch pre-filled
        func = functools.partial(process_batch, model_name, model_uuid, db_path=db_path)
        executor.map(func, batches)

    conn.close()
    print(f"Model '{model_name}' with label '{label}', using chunking method '{chunking_method}' and size '{chunking_size}', added to the database.")

def compute_query_embedding(model_name: str, query: str) -> torch.Tensor:
    """
    Compute the embedding for a query using the specified model.
    """
    model = SentenceTransformer(model_name, device="cpu")
    query_embedding = model.encode(query, convert_to_tensor=True)
    return query_embedding

def search_embeddings_by_similarity(conn, query_embedding: torch.Tensor, similarity_threshold: float = 0.75, label: str = None):
    """
    Search the embeddings table for entries that are more similar to the query embedding than the specified threshold.
    Optionally filter the search to only include entries linked to a specific label.

    Args:
        conn: The database connection object.
        query_embedding (torch.Tensor): The query embedding tensor.
        similarity_threshold (float, optional): The similarity threshold to filter entries. Defaults to 0.75.
        label (str, optional): The label to filter the search by. Defaults to None.

    Returns:
        list: A list of tuples containing the law entry UUIDs and their corresponding similarity scores above the threshold,
              sorted by similarity score in descending order.
    """
    cursor = conn.cursor()
    # If a label is provided, first find the corresponding label_uuid
    label_uuid = None
    if label:
        cursor.execute("SELECT label_uuid FROM labels WHERE label = ?", (label,))
        label_row = cursor.fetchone()
        if label_row:
            label_uuid = label_row[0]
        else:
            print(f"No label found with text '{label}'.")
            return []

    # Modify the query based on whether a label_uuid has been found
    if label_uuid:
        cursor.execute("""
            SELECT e.text_uuid, e.embedding, e.char_start, e.char_end
            FROM embeddings e
            INNER JOIN cluster_label_link cll ON e.text_uuid = cll.text_uuid
            WHERE cll.label_uuid = ?
        """, (label_uuid,))
    else:
        cursor.execute("SELECT text_uuid, embedding, char_start, char_end FROM embeddings")

    corpus_embeddings = []
    text_uuids = []
    char_starts = []
    char_ends = []
    for text_uuid, embedding_blob, char_start, char_end in cursor.fetchall():
        embedding = torch.Tensor(numpy.frombuffer(embedding_blob, dtype=numpy.float32))
        corpus_embeddings.append(embedding)
        text_uuids.append(text_uuid)
        char_starts.append(char_start)
        char_ends.append(char_end)

    corpus_embeddings_tensor = torch.stack(corpus_embeddings)
    cos_scores = util.cos_sim(query_embedding, corpus_embeddings_tensor)[0]

    # Filter results by similarity threshold and sort by score
    similar_entries = [(text_uuids[idx], score.item(), char_starts[idx], char_ends[idx])
                       for idx, score in enumerate(cos_scores) if score.item() >= similarity_threshold]
    similar_entries.sort(key=lambda x: x[1], reverse=True)  # Sort by similarity score in descending order

    return similar_entries

def search_embeddings(conn, query_embedding: torch.Tensor, model_name: str, top_k: int = 5, included_labels: list = None, excluded_labels: list = None):
    """
    Search the embeddings table for the top-k most similar entries to the query embedding.
    Optionally filter the search to only include entries linked to specific labels and exclude certain labels.

    Args:
        conn: The database connection object.
        query_embedding (torch.Tensor): The query embedding tensor.
        top_k (int, optional): The number of top similar entries to return. Defaults to 5.
        included_labels (list, optional): List of label_uuids to include in the search.
        excluded_labels (list, optional): List of label_uuids to exclude from the search.

    Returns:
        list: A list of tuples containing the law entry UUIDs and their corresponding similarity scores.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT uuid FROM nlp_model WHERE model = ?", (model_name,))
    model_row = cursor.fetchone()
    if not model_row:
        print(f"No model found with name '{model_name}'.")
        return []
    model_uuid = model_row[0]

    # Build the SQL query dynamically based on included and excluded labels
    include_condition = ""
    exclude_condition = ""
    params = []

    if included_labels:
        placeholders = ','.join('?' for _ in included_labels)
        include_condition = f"INNER JOIN text_label_link tll_included ON e.text_uuid = tll_included.text_uuid AND tll_included.label_uuid IN ({placeholders})"
        params.extend(included_labels)

    if excluded_labels:
        placeholders = ','.join('?' for _ in excluded_labels)
        exclude_condition = f"LEFT JOIN text_label_link tll_excluded ON e.text_uuid = tll_excluded.text_uuid AND tll_excluded.label_uuid IN ({placeholders})"
        params.extend(excluded_labels)

    params.append(model_uuid)

    # Prepare the SQL query
    query = f"""
        SELECT e.text_uuid, e.embedding, e.char_start, e.char_end
        FROM embeddings e
        {include_condition}
        {exclude_condition}
        WHERE e.model_uuid = ?  -- Filter by model_uuid
    """

    where_clauses = []
    if excluded_labels:
        where_clauses.append(f"tll_excluded.label_uuid IS NULL")
    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)

    if included_labels:
        query += " GROUP BY e.text_uuid HAVING COUNT(DISTINCT tll_included.label_uuid) = ?"
        params.append(len(included_labels))

    # Execute the SQL query
    cursor.execute(query, params)

    corpus_embeddings = []
    text_uuids = []
    char_starts = []
    char_ends = []
    for text_uuid, embedding_blob, char_start, char_end in cursor.fetchall():
        embedding = torch.Tensor(numpy.frombuffer(embedding_blob, dtype=numpy.float32))
        corpus_embeddings.append(embedding)
        text_uuids.append(text_uuid)
        char_starts.append(char_start)
        char_ends.append(char_end)

    if not corpus_embeddings:
        return []

    corpus_embeddings_tensor = torch.stack(corpus_embeddings)
    cos_scores = util.cos_sim(query_embedding, corpus_embeddings_tensor)[0]
    top_results = torch.topk(cos_scores, k=min(top_k, len(corpus_embeddings)))

    similar_entries = []
    for score, idx in zip(top_results[0], top_results[1]):
        similar_entries.append((text_uuids[idx], score.item(), char_starts[idx], char_ends[idx]))

    return similar_entries

def print_similar_entries(db_path: str, similar_entries):
    """
    Print out the text of the law entries for the top-k results and close the database connection.

    Args:
        conn: The database connection object.
        similar_entries: A list of tuples containing the law entry UUIDs and their corresponding similarity scores.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        for text_uuid, score, char_start, char_end in similar_entries:
            cursor.execute("SELECT text FROM law_entries WHERE uuid = ?", (text_uuid,))
            text = cursor.fetchone()[0]
            print(f"{text} (Score: {score:.4f}, Start: {char_start}, End: {char_end})")
    finally:
        conn.close()

def perform_search_by_similarity(db_path: str, model_name: str, query: str, percent: int = 50, label: str = None) -> list:
    """
    Perform a search over the embeddings table using cosine similarity and return the similar entries.

    Args:
        db_path (str): The path to the SQLite database.
        model_name (str): The name of the model to use for computing the query embedding.
        query (str): The query string to search for.
        top_k (int): The number of top similar entries to return.

    Returns:
        list: A list of tuples containing the law entry UUIDs and their corresponding similarity scores.
    """
    conn = sqlite3.connect(db_path)
    scaled_percent = percent / 100.00
    query_embedding = compute_query_embedding(model_name, query)
    similar_entries = search_embeddings_by_similarity(conn, query_embedding, scaled_percent, label)
    print(similar_entries)
    conn.close()
    return similar_entries

def perform_search(db_path: str, model_name: str, query: str, top_k: int = 5, included_labels: list = None, excluded_labels: list = None) -> list:
    """
    Perform a search over the embeddings table using cosine similarity and return the similar entries.

    Args:
        db_path (str): The path to the SQLite database.
        model_name (str): The name of the model to use for computing the query embedding.
        query (str): The query string to search for.
        top_k (int): The number of top similar entries to return.
        included_labels (list): List of label_uuids to include in the search.
        excluded_labels (list): List of label_uuids to exclude from the search.

    Returns:
        list: A list of tuples containing the law entry UUIDs and their corresponding similarity scores.
    """
    conn = sqlite3.connect(db_path)
    query_embedding = compute_query_embedding(model_name, query)
    
    # Modify the search function to filter by included and excluded labels
    similar_entries = search_embeddings(conn, query_embedding, model_name, top_k, included_labels, excluded_labels)
    conn.close()
    return similar_entries

def list_models(db_path):
    """
    List all models and their labels from the nlp_model table.

    Args:
        db_path (str): The path to the SQLite database.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT model, label FROM nlp_model")
    models = cursor.fetchall()
    conn.close()
    return models

# def process_topics(db_path: str):
#     # Step 1: Fetch entries from the database
#     texts, uuids = fetch_entries(db_path)

#     # Step 2: Create a BERTopic model and fit it to the texts
#     topic_model = BERTopic()
#     topics, probs = topic_model.fit_transform(texts)

#     # Step 3: Insert the topic labels into the database
#     topic_info = topic_model.get_topic_info()
#     topic_names = topic_info['Name'].tolist()
#     for topic_name in topic_names:
#         insert_label(db_path, topic_name)

#     # Step 4: Store the cluster link entries in the database
#     document_info = topic_model.get_document_info(texts)
#     documents = document_info['Document'].tolist()
#     names = document_info['Name'].tolist()
#     for doc, name in zip(documents, names):
#         store_cluster_link_entry(db_path, doc, name)

    # # Optional: Use HDBSCAN for clustering with BERTopic
    # hdbscan_model = HDBSCAN(min_cluster_size=15, metric='euclidean', cluster_selection_method='eom', prediction_data=True)
    # topic_model_cluster = BERTopic(hdbscan_model=hdbscan_model)
    # topics_cluster, probs_cluster = topic_model_cluster.fit_transform(texts)

    # # Return the topic model information
    # return topic_model_cluster.get_topic_info()

# def process_topics_with_user_labels(db_path: str):
#     # Step 1: Fetch entries from the database
#     texts, labels, uuids = fetch_entries_with_user_labels(db_path)

#     # Step 2: Create a BERTopic model and fit it to the texts
#     topic_model = BERTopic()
#     topics, probs = topic_model.fit_transform(texts, y=labels)

#     # Step 3: Insert the topic labels into the database
#     topic_info = topic_model.get_topic_info()
#     topic_names = topic_info['Name'].tolist()
#     for topic_name in topic_names:
#         insert_label(db_path, topic_name)

#     # Step 4: Store the cluster link entries in the database
#     document_info = topic_model.get_document_info(texts)
#     documents = document_info['Document'].tolist()
#     names = document_info['Name'].tolist()
#     for doc, name in zip(documents, names):
#         store_cluster_link_entry(db_path, doc, name)

    # # Optional: Use HDBSCAN for clustering with BERTopic
    # hdbscan_model = HDBSCAN(min_cluster_size=15, metric='euclidean', cluster_selection_method='eom', prediction_data=True)
    # topic_model_cluster = BERTopic(hdbscan_model=hdbscan_model)
    # topics_cluster, probs_cluster = topic_model_cluster.fit_transform(texts)

    # # Return the topic model information
    # return topic_model_cluster.get_topic_info()

def create_parser() -> Callable:
    """
    Create and return a command line argument parser with two subparsers for 'create' and 'search' commands.

    This function follows the Command Pattern, encapsulating the operation
    of parsing command line arguments.

    Returns:
        Callable: A parser object used for parsing command line arguments.
    """
    parser = argparse.ArgumentParser(description="Process a label with a model or search for embeddings.")
    subparsers = parser.add_subparsers(dest='command', required=True)

    # Create subparser for the 'create' command
    create_parser = subparsers.add_parser('create', help='Create a new model entry and process a label.')
    create_parser.add_argument('model_name', type=str, help='The name of the model to use')
    create_parser.add_argument('label', type=str, help='The label to process')
    create_parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose logging')
    create_parser.add_argument('--chunk_method', type=str, choices=['sentence', 'word', 'char'], 
                               default='sentence', help='The chunking method (default: sentence)')
    create_parser.add_argument('--chunk_size', type=int, default=1, 
                               help='The chunking size (default: 1, must be a non-zero integer)')

    # Create subparser for the 'search' command
    search_parser = subparsers.add_parser('search', help='Search for embeddings using a model and a query.')
    search_parser.add_argument('model_name', type=str, help='The name of the model to use for searching')
    search_parser.add_argument('query', type=str, help='The query to search for')

    # Create subparser for the 'init-db' or 'init-db' command
    init_db_parser = subparsers.add_parser('init-db', help='Initialize the database and create necessary tables.')
    init_db_parser.add_argument('db_name', type=str, help='The name of the database to initialize')

    # Create subparser for the 'create-label' command
    create_label_parser = subparsers.add_parser('create-label', help='Insert a new label into the labels table.')
    create_label_parser.add_argument('label_text', type=str, help='The text of the label to insert')
    create_label_parser.add_argument('--color', type=str, default='blue', help='The color associated with the label (default: blue)')

    # Create subparser for the 'list-labels' command
    list_labels_parser = subparsers.add_parser('list-labels', help='List all labels in the labels table.')

    # Create subparser for the 'cluster' command
    cluster_parser = subparsers.add_parser('cluster', help='Cluster law entries based on their embeddings.')
    cluster_parser.add_argument('model_name', type=str, help='The name of the model to use for clustering')
    cluster_parser.add_argument('--min_community_size', type=int, default=25, help='Minimum number of entries to form a cluster (default: 25)')
    cluster_parser.add_argument('--threshold', type=float, default=0.75, help='Cosine similarity threshold for considering entries as similar (default: 0.75)')

    # Create subparser for the 'list-models' command
    list_models_parser = subparsers.add_parser('list-models', help='List all models and their labels from the nlp_model table.')

    return parser

if __name__ == "__main__":
    parser = create_parser()
    args = parser.parse_args()
    db_name = 'law_database.db'

    if args.command == 'create':
        create_database(db_name)
        # Validate chunking size if provided
        if args.chunk_size is not None and args.chunk_size <= 0:
            parser.error("Chunking size must be a non-zero integer")
        create_embedding(db_name, args.label, args.model_name, args.chunk_method, args.chunk_size, args.verbose)

    elif args.command == 'search':
        similar_entries = perform_search(db_name, args.model_name, args.query)
        print_similar_entries(db_name, similar_entries)
    
    elif args.command == 'init-db':
        create_database(args.db_name)
        print(f"Database '{args.db_name}' initialized successfully.")
    
    elif args.command == 'create-label':
        label_uuid = insert_label(db_name, args.label_text, args.color)
        print(f"Label '{args.label_text}' with UUID '{label_uuid}' inserted successfully.")

    elif args.command == 'list-labels':
        labels = list_labels(db_name)
        for label in labels:
            print(f"UUID: {label[0]}, Label: {label[1]}, Creation Time: {label[2]}, Color: {label[3]}")

    elif args.command == 'cluster':
            cluster_entries(db_name, args.model_name, args.min_community_size, args.threshold)

    elif args.command == 'list-models':
        models = list_models(db_name)
        for model, label in models:
            print(f"Model: {model}, Label: {label}")
