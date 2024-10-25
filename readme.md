# Legal Ontology

completly undocumented -- but maybe you'll find something burried here ? 

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

# Hyperplex
The project Hyperplex involves creating multimodal [machine-readable memeplexes](https://web.archive.org/web/20230314182803/http://www.susanblackmore.uk/wp-content/uploads/2017/05/JCS03.pdf) represented as directed hypergraph ontology logs. lol.

Best used with a gnn for which you have many options:
- [Ontology Management Engine](https://github.com/cyber-phys/ontology)
- [Ultra](https://github.com/DeepGraphLearning/ULTRA)
- ~[GNN-QE](https://github.com/cyber-phys/GNN-QE)~

## Crash Course on Ologs
[Ontology logs (ologs)](https://math.mit.edu/~dspivak/informatics/olog.pdf) are conceptual frameworks for organizing and representing knowledge in a structured and categorical way. They leverage the principles of category theory to create a map of interconnected concepts and relationships. In an olog, entities and their interrelations are precisely defined, with emphasis on clear and functional connections. This structured approach enables the creation of a rigorous and reusable knowledge base. Ologs are particularly useful for representing complex domains of knowledge in a way that is both precise and adaptable, allowing for the integration of new information and the connection of disparate ideas. They can be especially beneficial in scientific and academic contexts where clear, systematic representation of complex information is crucial.

[Ologs enable the construction of cross-domain analogies](https://arxiv.org/abs/1111.5297) that systematically map out nuanced relationships within a memeplex, allowing for machine-readable and multi-layered analysis of information.

![](linguistic_structure_category_theory.png)
*Ologs applied to generative linguistics*

![](functorial_analogy.png)
*Ologs used to form cross domain functorial analogies*

# Usage
Install [babaska](https://babashka.org)
## Set api keys
```
export OPEN_AI_KEY=""
expprt REPLICATE_API_TOKEN=""
```
## Loading arxiv papers into the DiHypergraph
This script integrate scholarly papers from arXiv into the DiHypergraph, enriching your memeplex with cutting-edge research and perspectives.
```
bb olog.clj https://arxiv.org/pdf/1102.1889.pdf
```
## Loading User Session into the DiHypergraph
This script captures screenshots at regular 5-second intervals and integrates them into a dynamic DiHypergraph. Each captured image undergoes semantic label generation using the powerful gpt-4-vision model, enriching the data with meaningful context and information.
```
bb auto-capture.clj
```

# Roadmap
Work is on going. The primary challenge is representing the geometry of information in the ontology graph consistently.

Feel free to make a PR if you have any ideas, email me at luc@sanative.ai if you wish to discuss further.

- [x] Add screen grabs to hypergraph
- [x] Add arXiv papers to the hypergraph
- [ ] Consistent formating of the ologs.

# Other attempts at constructing ologs with llms:
- [Olog Debate](https://github.com/cyber-phys/olog-debate)
- [olog-py](https://github.com/Continuum-Corporation/olog)

# Blog Posts on OLOGS:
- [An Intro into Ontology Logs (Ologs)](https://cyber-phys.com/blog/olog/)
- [Knowledge Graphs and Ologs: Enhancing AI Safety through Debate and Ontological Commitments](https://cyber-phys.com/blog/ai-alignment-through-ologs/)
