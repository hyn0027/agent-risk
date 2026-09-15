# Related works on ontology engineering / ontology learning

## Overview

- An ontology is a model about some environement we care about
  - e.g. slack has concepts channel, user, message; messages are related to channels in the sense that messages are sent to channels; channel has a property 'visibility' that can be either public or private; etc.
- Ontology engineering is about how to build/represent/eval/maintain ontology
- Ontology learning is about how to get ontologies from text/data/examples

## Basics

[1] Gruber, T. R. (1993). A translation approach to portable ontology specifications. Knowledge acquisition, 5(2), 199-220.

- Definition & Framing - what is ontology
- ***Conceptualization***: the objects, concepts, and other entities that are presumed to exist in some area of interest and the relationships that hold among them
- An ***ontology*** is an explicit specification of a ***conceptualization***... what 'exists' is exactly what can be represented
- This set of objects, and the formalized relationships among them, are reflected in the representational ***vocabulary*** with which a knowledge-based program represents knowledge

[2] Uschold, M., & Gruninger, M. (1996). Ontologies: Principles, methods and applications. The knowledge engineering review, 11(2), 93-136.

- Comprehensive introduction of ontologies w/ examples
- An ***ontology*** necessarily entails or embodies some sort of world view with respect to a given domain. The world view is often conceived as a set of concepts (e.g. entities, attributes, processes), their definitions and their inter-relationships; this is is referred to as a ***conceptualisation***. Such a conceptualisation may be implicit. The ontology is an explicit account or representation of (some part of) a conceptualisation
- Ontology can range from highly informatl (pure NL) to rigorously formal (formal language that support proofs)
- Ontologies are often used to:
  - Help communication by setting a shared language across people/organization/fields
  - Address inter-operability by having a "shared interface" between systems
  - Help system enginering by help figuring out specification (or req, depending on how formal an ontology is), enhance reliability (because formal checks are possible), and improve reusability

[3] Grüninger, M., & Fox, M. S. (1995). The role of competency questions in enterprise engineering. In Benchmarking—Theory and practice (pp. 22-31). Boston, MA: Springer US

- Specifically talks about ontology in 'enterprise', covering activity, time, causality, resources, cost, quality, etc.
- Takeaways (beside those enterprise-specific stuff): Before deciding what concepts an ontology should express, what do we want the ontology to help us do after all? The requirement on what an ontology is supposed to represent (e.g. tasks, solution, etc.), is called ***competency questions***.
- Competency questions is useful in deciding what to model and what to leave out (granularity in a sense?). They also serve as tests on whether an ontology is sufficient/correct.
- Building ontology should not start with listing nouns, but should start with real world needs and competency questions.

[4] Ontology Development 101: A Guide to Creating Your First Ontology (<https://protege.stanford.edu/publications/ontology_development/ontology101-noy-mcguinness.html>)

- Tutorial
- Classes are the focus of most ontologies. Classes describe concepts in the domain.
- Slots describe properties of classes and instances.
- In practical terms, developing an ontology includes:
  - defining classes in the ontology,
  - arranging the classes in a taxonomic (subclass–superclass) hierarchy,
  - defining slots and describing allowed values for these slots,
  - filling in the values for slots for instances.
- Steps
    1. Determine the domain & scope of the ontology
        - What is the ontology for? Competency questions.
    2. Consider reusing existing ontologies
    3. Enumerate important terms in the ontology
    4. Define the classes and the class hierachy
        - top-down/bottomup/combination
    5. Define the properties of classes - slots
    6. Define the facets of the slots
        - "data schema" for the value of slots
    7. Create instances

## Ontology Learning

[5] Wong, W., Liu, W., & Bennamoun, M. (2012). Ontology learning from text: A look back and into the future. ACM computing surveys (CSUR), 44(4), 1-36.

- Survey on traditional ontology learning (pre ML/LLM time)

[6] Babaei Giglou, H., D’Souza, J., & Auer, S. (2023, October). LLMs4OL: Large language models for ontology learning. In International semantic web conference (pp. 408-427). Cham: Springer Nature Switzerland.

- Use LLMs to generate ontologies

[7] Lippolis, A. S., Saeedizade, M. J., Keskisärkkä, R., Zuppiroli, S., Ceriani, M., Gangemi, A., ... & Nuzzolese, A. G. (2025, June). Ontology generation using large language models. In European semantic web conference (pp. 321-341). Cham: Springer Nature Switzerland.

[8] Li, J., Garijo, D., & Poveda-Villalón, M. (2026). Large language models for ontology engineering: a systematic literature review. Semantic Web, 17(4), 22104968261465514.

