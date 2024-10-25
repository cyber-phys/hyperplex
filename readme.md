# Legal Ontology

Note: We are using Lamda Stack on production/dev server

Setup Python Venv
```
python3 -m venv lambda-stack-with-tensorflow-pytorch --system-site-packages
```

Installing Selenium:
Install Chrome
```
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo dpkg -i google-chrome-stable_current_amd64.deb
sudo apt-get install -f  # This fixes any dependency issues from the previous command
```

Launch Server
```
source lambda-stack-with-tensorflow-pytorch/bin/activate
pnpm run dev
python server.py
sudo tailscale funnel --https 443 http://127.0.0.1:3000
sudo tailscale funnel --https 8443 http://127.0.0.1:8000
```

# Notes:
Somthing like [this](https://arxiv.org/pdf/2004.13821v1.pdf) but for chatgpt conversation flow:

![Multi Hop QA](./MULTI_HOP_QUESTION_ANSWERING.png)

**Entity Typing**

[Interpretable Entity Representations through Large-Scale Typing](https://arxiv.org/pdf/2005.00147.pdf)

**Legal Bert**

https://huggingface.co/nlpaueb/legal-bert-base-uncased

unfortunately this model is uncased, I would think cased would be more useful in legal tasks where defined terms are usually cased.

## Building out a knowledge graph
Entity Typing:
- requires the model to predict the fine-grained types of a set of free-form phrases given their context

Relation Extraction:
- the model identifies the specific semantic relationship between two entities within a provided sentence.

**Text 2 Triplet**
- [ERNIE 3.0](https://arxiv.org/pdf/2107.02137.pdf)
- [HORNET](https://arxiv.org/pdf/2107.02137.pdf)


**Knowledge Graph Completion**
- [Revisiting Inferential Benchmarks for Knowledge Graph Completion](https://export.arxiv.org/pdf/2306.04814v1.pdf)

**Hyper Relational Knowledge Graphs**
- [A Dataset for Hyper-Relational Extraction and a Cube-Filling Approach](https://arxiv.org/pdf/2211.10018.pdf)