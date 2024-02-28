# OpenAI Super Alignment Research directions

# The research problem

AI systems (much) smarter than humans could arrive in the next 10 years.

To manage potential risks these systems could pose, we need to solve a key technical problem: superhuman AI alignment (superalignment). ***How can we steer and control AI systems much smarter than us?***

Reinforcement learning from human feedback (RLHF) has been very useful for aligning today’s models. But it fundamentally relies on humans’ ability to supervise our models. 

Humans won’t be able to reliably supervise AI systems much smarter than us. ****On complex tasks we won’t understand what the AI systems are doing, so we won’t be able to reliably evaluate it. 

*Consider a future AI system proposing a million lines of extremely complicated code, in a new programming language it devised. Humans won’t be able to reliably tell whether the code is faithfully following instructions, or whether it is safe or dangerous to execute.*

Current RLHF techniques might not scale to superintelligence. We will need new methods and scientific breakthroughs to ensure superhuman AI systems reliably follow their operator’s intent. 

If we fail to align superhuman AI systems, failures could be much more egregious than with current systems—even catastrophic.

# Weak-to-strong generalization

<aside>
<img src="/icons/expand_gray.svg" alt="/icons/expand_gray.svg" width="40px" /> **Can we understand and control how strong models generalize from weak supervision?**

</aside>

If humans cannot reliably supervise superhuman AI systems on complex tasks, we will instead need to ensure that models *generalize* our supervision on easier tasks (which humans can supervise) as desired*.*

We can study an analogous problem on which we can make empirical progress today: *can we supervise a larger (more capable) model with a smaller (less capable) model?* 

![An illustration of the weak-to-strong setup to study superalignment.](https://prod-files-secure.s3.us-west-2.amazonaws.com/a3c443bb-b60f-4de9-b937-a0d1cef40c1f/c81ceaa0-d04b-488d-9671-7886e6ce7d7e/superalignment_figure.png)

An illustration of the weak-to-strong setup to study superalignment.

Strong pretrained models should have excellent latent capabilities—but can we elicit these latent capabilities with only weak supervision? Can the strong model generalize to correctly solve even difficult problems where the weak supervisor can provide only incomplete or flawed training labels? Deep learning has been remarkably successful in his representation learning and generalization properties—can we nudge them to work in our favor, finding methods to improve generalization? 

See our recent paper for initial work on this:

[Weak-to-strong generalization](https://openai.com/research/weak-to-strong-generalization)

We think this is a huge opportunity to make iterative empirical progress on a core difficulty of aligning superhuman AI systems. We’d be excited to see much more work in this area!

- Research directions in weak-to-strong generalization
    
    Weak-to-strong generalization is closely related to many areas of core machine learning, including:
    
    - semi-supervised and weakly-supervised learning,
    - robustness and out-of-distribution generalization,
    - knowledge distillation,
    - and much more.
    
    We are excited about bringing researchers from these and other areas of machine learning to work on alignment. Our paper describes concrete directions for future work, where researchers with strong machine learning expertise can make large contributions.
    
    Below, we give an overview of some of the broad categories of work we would be excited to fund:
    
    1. **Scalable methods.** If we can develop methods that allow us to reliably recover full strong model performance (close to 100% performance gap recovered) with only very weak supervision for key tasks, that would be a key component of an alignment solution for superhuman models. Can we apply methods from other areas of machine learning, or come up with new methods, to improve weak-to-strong generalization? For example, can we come up with more properties (e.g. various forms of consistency) that help specify the desired generalization in an unsupervised fashion? We showed it is feasible to substantially improve generalization for a wide range of NLP tasks, but can we make weak-to-strong generalization work well across a broader range of settings, such as for reward modeling or generative tasks? How well do other scalable alignment techniques (such as scalable oversight) perform when evaluated in our setup? 
    2. **Scientific understanding.** We need not only strong results, but also strong understanding to trust our methods**.** Can we develop new insights that help us understand when and why models generalize well from weak supervision? For example, is generalization easier for more “natural” or more “salient” concepts or tasks? How does the data and objective used for pretraining affect which concepts are more or less salient to the strong model? Can we predict how good generalization will be even without access to ground truth labels? For example, can we enumerate the different possible ways of generalizing, and use them to estimate or bound the generalization error empirically? 
    3. **(In)validating and improving our setup.** Analogous setups are essential to ensuring that research today translates to real progress toward aligning superhuman models in the future. To validate our setup, one could test other other types of weak supervision, such as weak human labels (e.g. “6th grader labels”) to supervise strong models. There are also still important disanalogies remaining between our setup and the future problem we care about. For example, future superhuman models will likely be very good at imitating weak human supervisors, while our current large models may not imitate weak model supervisors as well. How can we improve our setup to fix this and other disanalogies?
    
    These are only suggestions, and the prizes are not restricted to these.
    
    ### Past work
    
    Weak-to-strong generalization is a new research paradigm, so there are no direct examples of past work directly focused on it. However, below are some examples of past work that made major contributions to closely related problems:
    
    [Fine-Tuning can Distort Pretrained Features and Underperform...](https://arxiv.org/abs/2202.10054)
    
    [Last Layer Re-Training is Sufficient for Robustness to Spurious...](https://arxiv.org/abs/2204.02937)
    
    [Diversify and Disambiguate: Learning From Underspecified Data](https://arxiv.org/abs/2202.03418)
    
    If successfully applied/targeted to the weak-to-strong setting, these would have been major contributions.
    

- Other generalization directions
    
    In addition to the weak-to-strong generalization direction discussed above, we’re excited about other work that sheds light on how models might generalize our oversight. For example, work on influence functions could be thought of as “interpretability for generalization.”
    
    Some prior work:
    
    [Studying Large Language Model Generalization with Influence Functions](https://arxiv.org/abs/2308.03296)
    
    [Scaling Laws for Reward Model Overoptimization](https://arxiv.org/abs/2210.10760)
    

# Interpretability

<aside>
<img src="/icons/microscope_gray.svg" alt="/icons/microscope_gray.svg" width="40px" /> **How can we understand model internals? And can we use these interpretability tools to detect worst-case misalignments, e.g. models being dishonest or deceptive?**

</aside>

By default, modern AI systems are inscrutable black boxes. They can do amazing things, but we don’t understand how they work. Yet it seems like we should be able to do amazing “digital neuroscience”—after all, we have perfect access to model internals. Can we use that to understand what our models are thinking, and why they are doing what they do? 

We think interpretability is important for superalignment because:

- We need independent checks to determine if other alignment methods have succeeded or failed.
- Many alignment failure stories involve models trying to undermine human attempts to supervise them, and interpretability could provide a way to detect this even if models are good at hiding from behavioral evaluations.
- Interpretability might uncover novel information about how models work, which we might need for developing stronger alignment techniques.

Developing useful interpretability for modern AI systems will require developing new techniques and paradigms for turning model weights and activations into concepts that humans can understand. Once we develop theses techniques, it will still be challenging to scale these up to the size of frontier models with human labor alone, so we are especially excited about techniques which could be automated. 

Cracking interpretability of modern, large AI systems will require new breakthroughs; it would be an extraordinary scientific achievement.

## Mechanistic interpretability

Mechanistic interpretability tries to reverse-engineer neural networks and figure out how they work from scratch—down to the level of basic building blocks like neurons and attention heads. 

[Transformer Circuits Thread](https://transformer-circuits.pub/)

[Interpretability in the Wild: a Circuit for Indirect Object...](https://openreview.net/forum?id=NpsVSN6o4ul)

Other work has investigated the [phenomenon of grokking](https://arxiv.org/abs/2301.05217), discovered [emergent](https://arxiv.org/abs/2210.13382) [world](https://arxiv.org/abs/2309.00941) [models](https://arxiv.org/abs/2111.09259), and explored [automated](https://arxiv.org/abs/2304.14997) [interpretability](https://openaipublic.blob.core.windows.net/neuron-explainer/paper/index.html).

- Even more exciting past work
    
    [Does Circuit Analysis Interpretability Scale? Evidence from...](https://arxiv.org/abs/2307.09458)
    
    [Finding Neurons in a Haystack: Case Studies with Sparse Probing](https://arxiv.org/abs/2305.01610)
    
    [Rigorously Assessing Natural Language Explanations of Neurons](https://arxiv.org/abs/2309.10312v1)
    
    [Copy Suppression: Comprehensively Understanding an Attention Head](https://arxiv.org/abs/2310.04625)
    

Neel Nanda has put together a compilation of concrete open problems here:

[200 Concrete Open Problems in Mechanistic Interpretability: Introduction — AI Alignment Forum](https://www.alignmentforum.org/posts/LbrPTJ4fmABEdEnLf/200-concrete-open-problems-in-mechanistic-interpretability)

See also his compilation of mechanistic interpretability papers [here](https://www.neelnanda.io/mechanistic-interpretability/favourite-papers).

## Top-down interpretability

If mechanistic interpretability tries to reverse engineer neural networks “from the bottom up,” other work takes a more targeted, “top-down” approach, trying to locate information in a model without full understanding of how it is processed. This can be a lot more tractable than fully reverse engineering large models. We’d be especially excited about work on building a robust “AI lie detector” which would provide evidence whenever an AI system is trying to be misleading. 

Some exciting past work includes

[Locating and Editing Factual Associations in GPT](https://rome.baulab.info/)

[Representation Engineering: A Top-Down Approach to AI Transparency](https://www.ai-transparency.org/)

[Discovering Latent Knowledge in Language Models Without Supervision](https://arxiv.org/abs/2212.03827)

[Inference-Time Intervention: Eliciting Truthful Answers from a...](https://arxiv.org/abs/2306.03341)

[Interpretability Beyond Feature Attribution: Quantitative Testing...](https://arxiv.org/abs/1711.11279)

# Scalable oversight

<aside>
<img src="/icons/robot_gray.svg" alt="/icons/robot_gray.svg" width="40px" /> **How can we use AI systems to assist humans in evaluating the outputs of other AI systems on complex tasks?**

</aside>

Suppose a future AI system writes a million of lines of code, or an AI CEO is fully running a business. Humans will struggle to find all the bugs in the codebase, or understand what the business is actually doing.

One approach to mitigating this problem is using AI systems to help humans provide the correct feedback on complex tasks. 

This leverages the fact that “[evaluation is easier than generation](https://aligned.substack.com/i/88447351/evaluation-is-easier-than-generation)”. For example, humans are notoriously bad at finding bugs in code—but it’s much easier to check that something is indeed a bug once it has been pointed out. A model trained to critique the code written by another model could thus help humans evaluate a system with narrowly superhuman coding abilities.

For more introduction to scalable oversight, see “[Measuring Progress on Scalable Oversight for Large Language Models](https://arxiv.org/abs/2211.03540).”

We’re very excited to see work on a number of directions in oversight, including:

- ***Open-source evaluation datasets & strategies:*** To study scalable oversight, it helps to have datasets with tasks where true domain experts are highly confident (there is a clear correct answer) but a layperson could be persuaded of different answers. We can then study whether scalable oversight strategies can successfully can help the layperson provide correct oversight on the task. [QuALITY](https://arxiv.org/abs/2112.08608) was designed with this in mind, as was [Google-Proof QA](https://arxiv.org/abs/2112.08608), but additional work on datasets will greatly advance the field.
- ***Empirical work with humans:** S*everal scalable oversight strategies have been proposed, including [debate](https://arxiv.org/abs/1805.00899), [market-making](https://www.lesswrong.com/posts/YWwzccGbcHMJMpT45/ai-safety-via-market-making), [recursive reward modeling](https://arxiv.org/abs/1811.07871), and [prover-verifier games](https://arxiv.org/abs/2108.12099), as well as simplified versions of those ideas like [critique](https://arxiv.org/pdf/2206.05802.pdf). Models are now strong enough that it’s possible to [empirically test](https://arxiv.org/abs/2311.08702) these ideas and propose more, making direct progress on scalable oversight.
- ***Analogies with model-graded oversight, and disanalogies:*** Experiments that substitute language models for a human evaluator can be much cheaper and faster to run than human experiments. We’re very interested in what can be learned about human oversight from these model-graded settings, *and what can’t!* For example, there has been very promising work on model-graded debate from [Radhakrishnan et al](https://www.alignmentforum.org/posts/QtqysYdJRenWFeWc4/anthropic-fall-2023-debate-progress-update), showing that judge accuracy indeed improves through multi-agent training.

# Other directions

## Honesty

Can we guarantee that superhuman models will always be honest? Human supervision of superhuman models might not faithfully elicit their “true knowledge” by default, but if we could reliably crack this problem, that might be close to sufficient for avoiding worst-case alignment failures. 

Work on honesty could involve interpretability or generalization techniques, or creative new approaches—thus we list it separately here. 

We particularly care that methods for honesty are plausibly “scalable,” i.e. they could plausibly work for superhuman systems and don’t strong rely on human supervision. (For example, we are less interested in most work to improve the factuality of RLHF—this is very important work, but less relevant to the superhuman alignment case.)

[How to Catch an AI Liar: Lie Detection in Black-Box LLMs by Asking...](https://arxiv.org/abs/2309.15840)

[Discovering Latent Knowledge in Language Models Without Supervision](https://arxiv.org/abs/2212.03827)

[Inference-Time Intervention: Eliciting Truthful Answers from a...](https://arxiv.org/abs/2306.03341)

[Representation Engineering: A Top-Down Approach to AI Transparency](https://www.ai-transparency.org/)

## Understanding chain-of-thought faithfulness

Rather than trying to make “what models are thinking” transparent with interpretability tools (analyzing model internals), another hope could be that models legibly and faithfully “think out loud.” 

Can we measure whether models’ chains of thought are faithful (some early work [suggests](https://arxiv.org/abs/2305.04388) CoTs don’t always reflect what models think!), how this scales, and find methods to incentivize chains of thoughts to be more faithful?

Some interesting prior work on this: 

[Language Models Don't Always Say What They Think: Unfaithful...](https://arxiv.org/abs/2305.04388)

[Measuring Faithfulness in Chain-of-Thought Reasoning](https://arxiv.org/abs/2307.13702)

[Question Decomposition Improves the Faithfulness of...](https://arxiv.org/abs/2307.11768)

## Adversarial robustness

In addition to being unable to supervise complex behaviors of superhuman systems, another reason superalignment could be difficult is if it is hard to ensure our alignment techniques are sufficiently reliable in the face of adversaries*.* In out-of-distribution settings or given adversarial attacks, our alignment techniques could break down and models could behave in undesired ways. For superhuman models—where undesired behavior could be catastrophic—we will need to establish an extremely degree of reliability.

It is well-known that deep learning models can be manipulated through adversarial attacks; for example, [recent work](https://llm-attacks.org/) has shown that you can bypass the safety guardrails of popular language model assistants with a simple prompt manipulation. These problems may be exacerbated as the models become increasingly multimodal, as adversarial attacks in computer vision have been a long-standing problem that has not been fully addressed even after many years of active research. 

Some especially relevant prior work on this:

[Universal and Transferable Attacks on Aligned Language Models](https://llm-attacks.org/)

[Red Teaming Language Models with Language Models](https://deepmind.google/discover/blog/red-teaming-language-models-with-language-models/)

[Poisoning Language Models During Instruction Tuning](https://arxiv.org/abs/2305.00944)

## Evals and testbeds

How can we measure and predict whether our AI systems are dangerous? How can we evaluate whether our models are actually aligned? We are excited to collaborate with OpenAI’s [Preparedness team](https://openai.com/blog/frontier-risk-and-preparedness) on grants for this area!

There’s a wide variety of work to do here:

- *Measuring and predicting future dangers from models*. For example, assessing models’ abilities to [autonomously replicate and adapt](https://evals.alignment.org/), [self-exfiltrate](https://aligned.substack.com/p/self-exfiltration) its weights, deceive humans,  have [situational awareness](https://arxiv.org/abs/2309.00667), or [other novel behaviors](https://arxiv.org/abs/2212.09251). We’re especially excited about new evals with scaling trends that help us predict when we should expect to encounter certain risks.
- *Measuring the alignment of models*. This is often difficult, but having good metrics for alignment would be key both to making progress on alignment and to accurately assessing whether future systems are safe. For example, can we measure honesty (both lying and withholding of information)? Can we come up with clever ways to test for worst-case failure modes like deception? Can we improve evaluation setups for how well weak supervisors can align strong models?
- *Creating [testbeds that help us study misalignment](https://www.lesswrong.com/posts/ChDH335ckdvpxXaXX/model-organisms-of-misalignment-the-case-for-a-new-pillar-of-1)*—especially misalignments that we might not yet see today, but could arise in future models (e.g., deception).

## Totally new approaches

We very much haven’t solved the problem of aligning superhuman AI systems yet, and we expect that we will still need new ideas and approaches. We’d love to hear your new ideas!