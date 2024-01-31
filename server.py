from sanic import Sanic, response
from sanic_ext import Extend
from embedding import perform_search, list_labels
import sqlite3

app = Sanic("LexAid")
app.config.CORS_ORIGINS = "http://localhost:3000"
extend = Extend(app)

@app.get("/labels")
async def labels_handler(request):
    """
    Retrieve a list of labels and their associated colors from the labels table.
    ---
    operationId: listLabels
    tags:
      - labels
    responses:
      '200':
        description: A list of labels with their colors.
        content:
          application/json:
            schema:
              type: array
              items:
                type: object
                properties:
                  label_uuid:
                    type: string
                    description: The unique identifier for the label.
                  label:
                    type: string
                    description: The name of the label.
                  creation_time:
                    type: string
                    format: date-time
                    description: The creation time of the label.
                  color:
                    type: string
                    description: The color associated with the label.
    """
    labels = list_labels('law_database_old.db')
    return response.json([{
        'label_uuid': label[0],
        'label': label[1],
        'creation_time': label[2],
        'color': label[3]
    } for label in labels])

@app.post("/search")
async def search_handler(request):
    """
    Perform a search over the embeddings table using cosine similarity and return the similar entries with additional details.
    ---
    operationId: searchEmbeddings
    tags:
      - search
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            properties:
              model_name:
                type: string
                description: The name of the model to use for computing the query embedding.
              query:
                type: string
                description: The query string to search for.
              top_k:
                type: integer
                description: The number of top similar entries to return.
                default: 5
              label:
                type: string
                description: The label associated with the law entry.
                default: None
    responses:
      '200':
        description: A list of similar entries based on the query, with additional details for each entry.
        content:
          application/json:
            schema:
              type: array
              items:
                type: object
                properties:
                  law_entry_uuid:
                    type: string
                    description: The unique identifier for the law entry.
                  score:
                    type: number
                    format: float
                    description: The similarity score between the query and the law entry.
                  text:
                    type: string
                    description: The text of the law entry.
                  char_start:
                    type: integer
                    description: The starting character position of the entry's text in the original document.
                  char_end:
                    type: integer
                    description: The ending character position of the entry's text in the original document.
                  code:
                    type: string
                    description: The code associated with the law entry.
                  section:
                    type: number
                    description: The section number of the law entry.
                  amended:
                    type: string
                    description: Information about any amendments to the law entry.
                  url:
                    type: string
                    description: The URL to the full text of the law entry.
    """
    body = request.json
    model_name = body.get("model_name", "")
    query = body.get("query", "")
    top_k = body.get("top_k", 5)
    label = body.get("label", None) 

    print(label)

    # Assuming 'db_path' is a global variable or retrieved from configuration
    db_path = 'law_database_old.db'
    similar_entries = perform_search(db_path, model_name, query, top_k, label)
    # Fetch the text for each similar entry
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    detailed_entries = []
    for law_entry_uuid, score, char_start, char_end in similar_entries:
        cursor.execute("""
            SELECT text, char_start, char_end, code, section, amended, url 
            FROM law_entries 
            JOIN embeddings ON law_entries.uuid = embeddings.law_entry_uuid 
            WHERE law_entries.uuid = ?
        """, (law_entry_uuid,))
        entry = cursor.fetchone()
        detailed_entries.append({
            'law_entry_uuid': law_entry_uuid,
            'score': score,
            'text': entry[0],
            'char_start': char_start,
            'char_end': char_end,
            'code': entry[3],
            'section': entry[4],
            'amended': entry[5],
            'url': entry[6]
        })
    conn.close()
    return response.json(detailed_entries)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)