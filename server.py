from sanic import Sanic, response
from sanic_ext import Extend
from embedding import perform_search, list_labels, insert_user_label_text, process_topics, process_topics_with_user_labels, get_user_labels
import sqlite3
from chatgpt_db_manager import connect_db, fetch_chats, fetch_topics, fetch_chat_topics, fetch_chat_links, fetch_conversations, fetch_predicted_chat_links

app = Sanic("LexAid")
app.config.CORS_ORIGINS = ["https://luc-g7-7500.taildd8a6.ts.net", "http://localhost:3000"]
extend = Extend(app)

chat_db_path = 'chat_666.db'
law_db_path = 'law_database.db'

@app.get('/chats')
async def get_chats(request):
    conn = connect_db(chat_db_path)
    chats = fetch_chats(conn)
    conn.close()
    return response.json(chats)

@app.get('/topics')
async def get_topics(request):
    conn = connect_db(chat_db_path)
    topics = fetch_topics(conn)
    conn.close()
    return response.json(topics)

@app.get('/chat_topics')
async def get_chat_topics(request):
    conn = connect_db(chat_db_path)
    chat_topics = fetch_chat_topics(conn)
    conn.close()
    return response.json(chat_topics)

@app.get('/chat_links')
async def get_chat_links(request):
    conn = connect_db(chat_db_path)
    chat_links = fetch_chat_links(conn)
    conn.close()
    return response.json(chat_links)

@app.get('/predicted_links')
async def get_predict_links(request):
    conn = connect_db(chat_db_path)
    predict_links = fetch_predicted_chat_links(conn)
    conn.close()
    return response.json(predict_links)

@app.get("/conversations")
async def conversations_handler(request):
    """
    Retrieve a list of conversations from the database and return them as JSON,
    using the fetch_table_data function for consistency with other endpoints.
    """
    conn = connect_db(chat_db_path)
    conversations = fetch_conversations(conn)
    conn.close()
    return response.json(conversations)

@app.get("/user_labels")
async def user_labels_handler(request):
    """
    Retrieve a list of user labels from the database and return them as JSON.
    ---
    operationId: listUserLabels
    tags:
      - labels
    responses:
      '200':
        description: A list of user labels.
        content:
          application/json:
            schema:
              type: array
              items:
                type: string
                description: The name of the user label.
    """
    labels = get_user_labels(law_db_path)
    return response.json(labels)

@app.post("/add_user_label")
async def add_user_label(request):
    """
    Add a user label to the database.
    ---
    operationId: addUserLabel
    tags:
      - labels
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            properties:
              label_name:
                type: string
                description: The name of the label to add.
              text_uuid:
                type: string
                description: The UUID of the text to label.
              char_start:
                type: integer
                description: The starting character position of the label in the text.
              char_end:
                type: integer
                description: The ending character position of the label in the text.
    responses:
      '200':
        description: Confirmation that the label has been added.
        content:
          application/json:
            schema:
              type: object
              properties:
                success:
                  type: boolean
                  description: True if the label was successfully added, false otherwise.
                message:
                  type: string
                  description: A message detailing the result of the operation.
    """
    body = request.json
    label_name = body.get("label_name", "")
    text_uuid = body.get("text_uuid", "")
    char_start = body.get("char_start", 0)
    char_end = body.get("char_end", 0)

    try:
        insert_user_label_text(law_db_path, label_name, text_uuid, char_start, char_end)
        print("Added label")
        return response.json({"success": True, "message": "Label added successfully."})
    except Exception as e:
        return response.json({"success": False, "message": str(e)})
  
@app.post("/process_topics")
async def process_topics_handler(request):
    """
    Process topics by creating a BERTopic model, fitting it to the texts,
    inserting topic labels into the database, and storing cluster link entries.
    ---
    operationId: processTopics
    tags:
      - topics
    responses:
      '200':
        description: Success message after processing topics.
        content:
          application/json:
            schema:
              type: object
              properties:
                success:
                  type: boolean
                  description: True if the topics were processed successfully, false otherwise.
                message:
                  type: string
                  description: A message detailing the result of the operation.
    """
    try:
        # Assuming process_topics is a function defined in the embedding module
        # and it performs all the steps as required.
        process_topics(law_db_path)
        return response.json({"success": True, "message": "Topics processed successfully."})
    except Exception as e:
        return response.json({"success": False, "message": str(e)})
    
@app.post("/process_topics_with_user_labels")
async def process_topics_with_user_labels_handler(request):
    """
    Process topics and user labels by creating a BERTopic model, fitting it to the texts,
    inserting topic labels and user labels into the database, and storing cluster link entries.
    ---
    operationId: processTopicsWithUserLabels
    tags:
      - topics
      - labels
    responses:
      '200':
        description: Success message after processing topics and user labels.
        content:
          application/json:
            schema:
              type: object
              properties:
                success:
                  type: boolean
                  description: True if the topics and user labels were processed successfully, false otherwise.
                message:
                  type: string
                  description: A message detailing the result of the operation.
    """
    try:
        # This function should be defined in the embedding module and should
        # include the logic for processing user labels along with topics.
        process_topics_with_user_labels(law_db_path)
        return response.json({"success": True, "message": "Topics and user labels processed successfully."})
    except Exception as e:
        return response.json({"success": False, "message": str(e)})

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
    labels = list_labels(law_db_path)
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
    
    similar_entries = perform_search(law_db_path, model_name, query, top_k, label)
    # Fetch the text for each similar entry
    conn = sqlite3.connect(law_db_path)
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