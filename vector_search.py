import math

def add_item(db, url, embedding):
    item={}
    item['url'] = url
    item['embedding'] = embedding
    store.append(item)

def norm(a):
    sum = 0
    for a_s in a:
        sum += a_s^2
    return(math.sqrt(sum))

def similarity(a, b):
    dot = 0
    for a_s in a:
        for b_s in b:
            dot += (a_s * b_s)
    return dot/(norm(a)*norm(b))

def search(db, query, top_k):
    results = []

    for i, d in enumerate(db):
        if len(results) < top_k:
            results.append(d['embedding'])
        else:
            sim = similarity(query, d['embedding'])
            if sim > results[0]:
                results[0] = d['embedding']
                results.sort()

    return results

store = []
add_item(store, "test", [0,0.11,0.2,0.55])
add_item(store, "test1", [0.2,.11,0.2,0.55])
add_item(store, "test2", [0.3,0.11,0.27,0.755])
add_item(store, "test3", [0,0.11,0.2,0.55])
add_item(store, "test4", [0.77,0.11,0.32,0.575])
add_item(store, "test5", [0.6,11,0.25,0.5555])

q = [0.77,0.11,0.32,0.575]
out = search(store, q, 2)
print(out)
