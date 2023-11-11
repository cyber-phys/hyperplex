# hyperdeath
A screen shot is taken every 5 seconds which is added to a temporal evolving DiHypergraph, the image is sent to gpt-4-vision in order to genreate a rich semantic label.  
## Useage
Set openai key
```
export OPEN_AI_KEY=""
```
Then run babaska script
```
bb auto-capture.clj
```
