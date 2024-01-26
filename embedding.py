import sqlite3
import argparse
from typing import Callable
from uuid import uuid4
import concurrent.futures
from sentence_transformers import SentenceTransformer
import itertools
import functools

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

    conn.commit()
    conn.close()

def fetch_law_entries(conn, batch_size=1000):
    """
    Generator function to yield batches of law entries from the database.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT uuid, text FROM law_entries")
    while True:
        entries = cursor.fetchmany(batch_size)
        if not entries:
            break
        yield entries

def compute_embeddings(model_name, texts):
    """
    Pure function to compute embeddings for a list of texts using the specified model.
    """
    model = SentenceTransformer(model_name)
    embeddings = model.encode(texts, convert_to_tensor=False)
    return embeddings

def store_embeddings(conn, model_uuid, entries, embeddings):
    """
    Function to store embeddings in the database.
    """
    cursor = conn.cursor()
    for entry, embedding in zip(entries, embeddings):
        law_entry_uuid, _ = entry
        cursor.execute("""
            INSERT INTO embeddings (model_uuid, law_entry_uuid, creation_time, embedding)
            VALUES (?, ?, datetime('now'), ?)
        """, (model_uuid, law_entry_uuid, embedding.tobytes()))

def process_batch(model_name, model_uuid, batch, db_path):
    """
    Function to process a batch of entries, compute embeddings, and store them in the database.
    """
    _, texts = zip(*batch)
    embeddings = compute_embeddings(model_name, texts)
    conn = sqlite3.connect(db_path)
    store_embeddings(conn, model_uuid, batch, embeddings)
    conn.commit()
    conn.close()

def create_embedding(db_path, label, model_name, chunking_method, chunking_size):
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
    batches = fetch_law_entries(conn)
    with concurrent.futures.ThreadPoolExecutor() as executor:
        # Use functools.partial to create a new function with some parameters of process_batch pre-filled
        func = functools.partial(process_batch, model_name, model_uuid, db_path=db_path)
        executor.map(func, batches)

    conn.close()
    print(f"Model '{model_name}' with label '{label}', using chunking method '{chunking_method}' and size '{chunking_size}', added to the database.")

# The rest of the file remains unchanged

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
    create_parser.add_argument('--chunk_method', type=str, choices=['sentence', 'word', 'char'], 
                               default='sentence', help='The chunking method (default: sentence)')
    create_parser.add_argument('--chunk_size', type=int, default=1, 
                               help='The chunking size (default: 1, must be a non-zero integer)')

    # Create subparser for the 'search' command
    search_parser = subparsers.add_parser('search', help='Search for embeddings using a model and a query.')
    search_parser.add_argument('model_name', type=str, help='The name of the model to use for searching')
    search_parser.add_argument('query', type=str, help='The query to search for')

    return parser

if __name__ == "__main__":
    parser = create_parser()
    args = parser.parse_args()
    db_name = 'law_database_old.db'

    if args.command == 'create':
        setup_database(db_name)
        # Validate chunking size if provided
        if args.chunk_size is not None and args.chunk_size <= 0:
            parser.error("Chunking size must be a non-zero integer")
        create_embedding(db_name, args.label, args.model_name, args.chunk_method, args.chunk_size)
    elif args.command == 'search':
        # Here you would add the logic to handle the 'search' command
        print("TODO: Implement search logic")