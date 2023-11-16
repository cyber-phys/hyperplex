# hyperplex
This project captures screenshots at regular 5-second intervals and integrates them into a dynamic DiHypergraph. Each captured image undergoes semantic label generation using the powerful gpt-4-vision model, enriching the data with meaningful context and information.
## Usage
Set api keys
```
export OPEN_AI_KEY=""
expprt REPLICATE_API_TOKEN=""
```
Then run babaska script
```
bb auto-capture.clj
```
