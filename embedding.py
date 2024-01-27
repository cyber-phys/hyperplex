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

    conn.commit()
    conn.close()

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

def search_embeddings(conn, query_embedding: torch.Tensor, top_k: int = 5):
    """
    Search the embeddings table for the top-k most similar entries to the query embedding.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT law_entry_uuid, embedding FROM embeddings")
    corpus_embeddings = []
    law_entry_uuids = []
    for law_entry_uuid, embedding_blob in cursor.fetchall():
        embedding = torch.Tensor(numpy.frombuffer(embedding_blob, dtype=numpy.float32))
        corpus_embeddings.append(embedding)
        law_entry_uuids.append(law_entry_uuid)

    corpus_embeddings_tensor = torch.stack(corpus_embeddings)
    cos_scores = util.cos_sim(query_embedding, corpus_embeddings_tensor)[0]
    top_results = torch.topk(cos_scores, k=top_k)

    similar_entries = []
    for score, idx in zip(top_results[0], top_results[1]):
        similar_entries.append((law_entry_uuids[idx], score.item()))

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
        for law_entry_uuid, score in similar_entries:
            cursor.execute("SELECT text FROM law_entries WHERE uuid = ?", (law_entry_uuid,))
            text = cursor.fetchone()[0]
            print(f"{text} (Score: {score:.4f})")
    finally:
        conn.close()

def perform_search(db_path: str, model_name: str, query: str, top_k: int = 5) -> list:
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
    similar_entries = search_embeddings(conn, query_embedding, top_k)
    conn.close()
    return similar_entries

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
        create_embedding(db_name, args.label, args.model_name, args.chunk_method, args.chunk_size, args.verbose)
    elif args.command == 'search':
        similar_entries = perform_search(db_name, args.model_name, args.query)
        print_similar_entries(db_name, similar_entries)