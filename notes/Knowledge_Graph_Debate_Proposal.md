# Knowledge Graphs and Ologs: Enhancing AI Safety through Debate and Ontological Commitments
Submitted to OpenAI Superalignment Fastgrants on February 18th, 2024

Authors:
- Luc Chartier
- Abizer Lokhandwala

## Short Description
- Knowledge graphs and ontology logs (ologs) hold promise as methods for scalably verifying truthfulness in a weak-to-strong generalization model of alignment
Methods exist in the research literature that allow for the creation of ologs from arbitrary unstructured text

- We propose using the debate/doubly-efficient debate alignment strategy proposed by Irving et al (2018) and Brown-Cohen et al (2023), but augmenting the verifier oracle by having it build KG/olog representations from the unstructured text of the debate log, and comparing these against a ground-truth KG (which is much less computationally expensive than inference) to verify true or false claims

- If the olog of a debate agent’s response indicates the existence of nodes or edges that are not present in our ground-truth KG (or denies existences we know are present), we’ve either discovered new knowledge (and the ground truth should be updated) or we’ve discovered a lie/mistake, meeting the objective of the debate alignment framework

- By forcing agents to make ontological commitments, we are able to find inconsistencies in reasoning and turn this into an objective that can optimized out in training

- In high-risk areas such as biomedicine, commercially-developed knowledge graphs present a strategic asset to counterbalance the limitations inherent in our Graph Neural Networks (GNNs) and the expertise gaps of non-specialist human validators. Utilizing these established knowledge graphs, we aim to bolster the validation framework, compensating for the GNN's uncertainties in claim verification and enhancing the analytical capacity of validators lacking domain-specific knowledge. 

- Incorporating ologs into the debate framework requires agents to make specific ontological commitments, unveiling inconsistencies in their reasoning throughout the training phase. This methodology involves the creation of two distinct types of ologs: a debate-level olog, which captures the immediate ontological structures formed during individual debates, and a temporal olog, which chronologically records the ontological commitments made across multiple training sessions. Through this dual-olog approach, we facilitate the detection of alignment deviations in models over time.

## Research Project
We are interested in exploring the applications of knowledge graphs to the alignment problem, and we believe this is a research direction that has a lot of potential in the context of weak-to-strong generalization and trustworthy AI.

A key claim in Irving et al’s 2018 paper “AI Safety via Debate” is that “in the debate game, it is harder to lie than to refute a lie.” This suggests a high-level approach to verifying alignment could be attempting to elicit lies from models and then verifying the truth of those statements. Brown-Cohen et al’s 2023 paper “Scalable AI Safety via Doubly-Efficient Debate” improves upon this, with the key idea being that “two polynomial-time provers compete
to convince a significantly more efficient verifier that they have correctly solved a computational problem that depends on black-box access to human judgements.” This protocol requires us to provide two things: a “significantly more efficient verifier” and “black-box access to human judgements.” We propose the following to satisfy those requirements.

The preprint “Zero-Shot Fact-Checking with Semantic Triples and Knowledge Graphs” by Yuan and Vlachos (2023) introduces a method to verify facts based on comparing triples extracted from a language model’s response to a ground-truth knowledge graph via a voting mechanism that returns supports/refutes/”not enough information”. The extraction of facts from statements can be done reliably through models that are much smaller (and therefore more efficient) than the ones being tested, as can the comparison of the extracted facts to a ground-truth knowledge base. This scheme gives us the requirements we need above: the fact-extraction model is our highly efficient verifier, and the knowledge graph check represents black box access to human judgements. The voting mechanism gives us further efficiency gains, as it reduces the number of debate rounds that need to be manually checked by a human verifier to only those that have “not enough information” results.

Our intention is to build a version of the doubly-efficient debate framework that uses knowledge-graph grounded fact-checking in the implementation of the verifier, and evaluate the performance and efficiency of this system for suitability in a superalignment context. 

## Connection to alignment of superhuman AI systems
If we can construct a reliable system to perform the debate and oracle verification task (extraction of facts and comparison to knowledge base to return an answer), it can be used to implement a training objective for superalignment, where the use of a weaker model that only needs to verify the outputs of stronger models can incentivize the production of interpretable responses (interpretable by a model that humans know to be aligned, even if the overall statement is beyond human capacity to interpret). Furthermore, we believe we can use the graph construction phase of the verification to implement quasilinguistic neural representations (QNRs) that themselves possess value from an interpretability point of view.