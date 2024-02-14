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
nltk.download('punkt')

def setup_database(db_path: str) -> None:
    """
    Set up the SQLite database and create tables if they do not exist.

    Args:
        db_path (str): The file path to the SQLite database.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create nlp_model table if it does not exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS nlp_model (
            uuid TEXT PRIMARY KEY,
            model TEXT NOT NULL,
            label TEXT NOT NULL UNIQUE,
            chunking_method TEXT CHECK(chunking_method IN ('sentence', 'word', 'char')) NOT NULL,
            chunking_size INTEGER NOT NULL
        );
    """)

    # Create embeddings table if it does not exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS embeddings (
            model_uuid TEXT NOT NULL,
            law_entry_uuid TEXT NOT NULL,
            creation_time TEXT NOT NULL,
            char_start INTEGER NOT NULL,
            char_end INTEGER NOT NULL,
            embedding BLOB NOT NULL,
            FOREIGN KEY(model_uuid) REFERENCES nlp_model(uuid),
            FOREIGN KEY(law_entry_uuid) REFERENCES law_entries(uuid)
        );
    """)

    # SQL statement to create the labels table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS labels (
            label_uuid TEXT PRIMARY KEY,
            label TEXT NOT NULL UNIQUE,
            representations TEXT,
            creation_time TEXT NOT NULL,
            color TEXT DEFAULT 'blue'
        );
    """)

    # SQL statement to create the label_embeddings table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cluster_label_link (
            label_uuid TEXT NOT NULL,
            law_entry_uuid TEXT NOT NULL,
            creation_time TEXT NOT NULL,
            FOREIGN KEY(label_uuid) REFERENCES labels(label_uuid),
            FOREIGN KEY(law_entry_uuid) REFERENCES law_entries(uuid)
        );
    """)

    # SQL statement to create the label_embeddings table
    cursor.execute("""
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
    """)

    conn.commit()
    conn.close()

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

def store_cluster_link_entry(db_path: str, text: str, label_name: str) -> None:
    """
    Store an entry in the cluster_label_link table by finding the corresponding label_uuid and law_entry_uuid.

    Args:
        db_path (str): The path to the SQLite database.
        text (str): The text of the law entry.
        label_name (str): The name of the label.

    Returns:
        None
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Find the label_uuid for the given label_name
        cursor.execute("SELECT label_uuid FROM labels WHERE label = ?", (label_name,))
        label_result = cursor.fetchone()
        if not label_result:
            raise ValueError(f"No label found with name '{label_name}'.")

        label_uuid = label_result[0]

        # Find the law_entry_uuid for the given text
        cursor.execute("SELECT uuid FROM law_entries WHERE text = ?", (text,))
        entry_result = cursor.fetchone()
        if not entry_result:
            raise ValueError(f"No law entry found with the given text.")

        law_entry_uuid = entry_result[0]

        # Insert into cluster_label_link table
        cursor.execute("""
            INSERT INTO cluster_label_link (label_uuid, law_entry_uuid, creation_time)
            VALUES (?, ?, datetime('now'))
        """, (label_uuid, law_entry_uuid))

        conn.commit()
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
    finally:
        conn.close()

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
    cursor.execute("SELECT law_entry_uuid, embedding FROM embeddings")
    entries = cursor.fetchall()
    cursor.execute("SELECT model FROM nlp_model WHERE label = ?", (model_name,))
    model_name_row = cursor.fetchone()
    conn.close()

    model_name = model_name_row[0]
    model = SentenceTransformer(model_name)

    if not model_name_row:
        print(f"No model found with label '{model_name}'.")
        return
        
    # Extract embeddings and convert them to tensors
    law_entry_uuids = [entry[0] for entry in entries]
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
            print("\tUUID: ", law_entry_uuids[entry_id])
    
    return

def insert_label(db_path, label_text, color='blue'):
    """
    Insert a new label into the labels table.

    Args:
        conn: The database connection object.
        label_text (str): The text of the label to insert.
        color (str, optional): The color associated with the label.

    Returns:
        str: The UUID of the inserted label.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    label_uuid = str(uuid4())
    cursor.execute("""
        INSERT INTO labels (label_uuid, label, creation_time, color)
        VALUES (?, ?, datetime('now'), ?)
    """, (label_uuid, label_text, color))
    conn.commit()
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
    cursor.execute("SELECT label_uuid, label, creation_time, color FROM labels")
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
            law_entry_uuid, text = entry
            char_start = 0
            if chunking_method == 'sentence':
                sentences = sent_tokenize(text)
                for i in range(0, len(sentences), chunking_size):
                    chunk = ' '.join(sentences[i:i+chunking_size])
                    char_end = char_start + len(chunk)
                    chunked_entries.append((law_entry_uuid, chunk, char_start, char_end))
                    char_start = char_end + 1  # +1 for the space after each chunk
            elif chunking_method == 'word':
                words = text.split()
                for i in range(0, len(words), chunking_size):
                    chunk = ' '.join(words[i:i+chunking_size])
                    char_end = char_start + len(chunk)
                    chunked_entries.append((law_entry_uuid, chunk, char_start, char_end))
                    char_start = char_end + 1  # +1 for the space after each chunk
            elif chunking_method == 'char':
                for i in range(0, len(text), chunking_size):
                    chunk = text[i:i+chunking_size]
                    char_end = char_start + len(chunk)
                    chunked_entries.append((law_entry_uuid, chunk, char_start, char_end))
                    char_start = char_end
        yield chunked_entries

def compute_embeddings(model_name, texts):
    """
    Pure function to compute embeddings for a list of texts using the specified model.
    """
    model = SentenceTransformer(model_name)
    embeddings = model.encode(texts, convert_to_tensor=False)
    return embeddings

def store_embeddings(conn, model_uuid, entries_with_positions):
    """
    Function to store embeddings in the database along with their character start and end positions.
    """
    cursor = conn.cursor()
    for law_entry_uuid, char_start, char_end, embedding in entries_with_positions:
        cursor.execute("""
            INSERT INTO embeddings (model_uuid, law_entry_uuid, creation_time, char_start, char_end, embedding)
            VALUES (?, ?, datetime('now'), ?, ?, ?)
        """, (model_uuid, law_entry_uuid, char_start, char_end, embedding.tobytes()))

def process_batch(model_name, model_uuid, batch, db_path):
    """
    Function to process a batch of entries, compute embeddings, and store them in the database.
    """
    # Unpack the batch to separate the texts and their corresponding char positions
    law_entry_uuids, texts, char_starts, char_ends = zip(*batch)
    embeddings = compute_embeddings(model_name, texts)
    conn = sqlite3.connect(db_path)
    # Combine the entries and their char positions with the computed embeddings
    entries_with_positions = zip(law_entry_uuids, char_starts, char_ends, embeddings)
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
    model = SentenceTransformer(model_name)
    query_embedding = model.encode(query, convert_to_tensor=True)
    return query_embedding

def search_embeddings(conn, query_embedding: torch.Tensor, top_k: int = 5, label: str = None):
    """
    Search the embeddings table for the top-k most similar entries to the query embedding.
    Optionally filter the search to only include entries linked to a specific label.

    Args:
        conn: The database connection object.
        query_embedding (torch.Tensor): The query embedding tensor.
        top_k (int, optional): The number of top similar entries to return. Defaults to 5.
        label (str, optional): The label to filter the search by. Defaults to None.

    Returns:
        list: A list of tuples containing the law entry UUIDs and their corresponding similarity scores.
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
            SELECT e.law_entry_uuid, e.embedding, e.char_start, e.char_end
            FROM embeddings e
            INNER JOIN cluster_label_link cll ON e.law_entry_uuid = cll.law_entry_uuid
            WHERE cll.label_uuid = ?
        """, (label_uuid,))
    else:
        cursor.execute("SELECT law_entry_uuid, embedding, char_start, char_end FROM embeddings")

    corpus_embeddings = []
    law_entry_uuids = []
    char_starts = []
    char_ends = []
    for law_entry_uuid, embedding_blob, char_start, char_end in cursor.fetchall():
        embedding = torch.Tensor(numpy.frombuffer(embedding_blob, dtype=numpy.float32))
        corpus_embeddings.append(embedding)
        law_entry_uuids.append(law_entry_uuid)
        char_starts.append(char_start)
        char_ends.append(char_end)

    corpus_embeddings_tensor = torch.stack(corpus_embeddings)
    cos_scores = util.cos_sim(query_embedding, corpus_embeddings_tensor)[0]
    top_results = torch.topk(cos_scores, k=top_k)

    similar_entries = []
    for score, idx in zip(top_results[0], top_results[1]):
        similar_entries.append((law_entry_uuids[idx], score.item(), char_starts[idx], char_ends[idx]))

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
        for law_entry_uuid, score, char_start, char_end in similar_entries:
            cursor.execute("SELECT text FROM law_entries WHERE uuid = ?", (law_entry_uuid,))
            text = cursor.fetchone()[0]
            print(f"{text} (Score: {score:.4f}, Start: {char_start}, End: {char_end})")
    finally:
        conn.close()

def perform_search(db_path: str, model_name: str, query: str, top_k: int = 5, label: str = None) -> list:
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
    query_embedding = compute_query_embedding(model_name, query)
    similar_entries = search_embeddings(conn, query_embedding, top_k, label)
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
        setup_database(db_name)
        # Validate chunking size if provided
        if args.chunk_size is not None and args.chunk_size <= 0:
            parser.error("Chunking size must be a non-zero integer")
        create_embedding(db_name, args.label, args.model_name, args.chunk_method, args.chunk_size, args.verbose)

    elif args.command == 'search':
        similar_entries = perform_search(db_name, args.model_name, args.query)
        print_similar_entries(db_name, similar_entries)
    
    elif args.command == 'init-db':
        setup_database(args.db_name)
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
