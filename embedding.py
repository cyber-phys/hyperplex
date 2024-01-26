import sqlite3
import argparse
from typing import Callable
from uuid import uuid4

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

def create_embedding(db_path: str, label: str, model_name: str, chunking_method: str, chunking_size: int) -> None:
    """
    Creates new embeddings with the specified model, chunking method, and chunking size.

    This function is a pure function that prints a message indicating
    that a model is being added to the database with the given label and
    the specified chunking method and size.

    Args:
        label (str): The label to process.
        model_name (str): The name of the model to use.
        chunking_method (str): The method used for chunking.
        chunking_size (int): The size of the chunks.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if an entry with the same label already exists
    cursor.execute("SELECT * FROM nlp_model WHERE label = ?", (label,))
    if cursor.fetchone():
        print(f"Error: An entry with the label '{label}' already exists.")
        return

    # Insert a new entry into the nlp_model table
    model_uuid = str(uuid4())
    cursor.execute("INSERT INTO nlp_model (uuid, model, label, chunking_method, chunking_size) VALUES (?, ?, ?, ?, ?)",
                   (model_uuid, model_name, label, chunking_method, chunking_size))
    print(f"Model '{model_name}' with label '{label}', using chunking method '{chunking_method}' and size '{chunking_size}', added to the database.")

    conn.commit()
    conn.close()

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
    create_parser.add_argument('label', type=str, help='The label to process')
    create_parser.add_argument('model_name', type=str, help='The name of the model to use')
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

    if args.command == 'create':
        setup_database('law_database_old.db')
        # Validate chunking size if provided
        if args.chunk_size is not None and args.chunk_size <= 0:
            parser.error("Chunking size must be a non-zero integer")
        create_embedding(args.label, args.model_name, args.chunk_method, args.chunk_size)
    elif args.command == 'search':
        # Here you would add the logic to handle the 'search' command
        print("TODO: Implement search logic")