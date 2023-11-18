# Hyperplex
The project Hyperplex involves creating multimodal [machine-readable memeplexes](https://web.archive.org/web/20230314182803/http://www.susanblackmore.uk/wp-content/uploads/2017/05/JCS03.pdf) represented as directed hypergraphs.
## Usage
Install [babaska](https://babashka.org)
### Set api keys
```
export OPEN_AI_KEY=""
expprt REPLICATE_API_TOKEN=""
```
### Loading arxiv papers into the DiHypergraph
This script integrate scholarly papers from arXiv into the DiHypergraph, enriching your memeplex with cutting-edge research and perspectives.
```
bb olog.clj https://arxiv.org/pdf/1102.1889.pdf
```
### Loading User Session into the DiHypergraph
This script captures screenshots at regular 5-second intervals and integrates them into a dynamic DiHypergraph. Each captured image undergoes semantic label generation using the powerful gpt-4-vision model, enriching the data with meaningful context and information.
```
bb auto-capture.clj
```

# Roadmap
Work is on going. The primarly challenge is representing the geometry of information in the ontology graph consistently.

Feel free to make a PR if you have any ideas, eamil me at luc@sanative.ai if you wish to discuss further.

- [x] Add screen grabs to hypergraph
- [x] Add arXiv papers to the hypergraph
- [ ] Consitant formating of the ologs. 
