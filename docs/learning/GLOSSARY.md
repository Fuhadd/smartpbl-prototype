# Glossary

- **GGUF**: The file format used by llama.cpp and Ollama for model weights and metadata. It supports quantised tensors.
- **Quantisation**: Storing model weights with fewer bits (e.g. 4-bit instead of 16-bit floats) to cut memory use and speed up inference, at a small cost in accuracy.
- **Q4_K_M**: A llama.cpp "k-quant" scheme: ~4-bit weights in blocks with per-block scales, medium size and quality variant. Typical for Ollama library models.
- **Unified memory**: Apple Silicon design where CPU and GPU share one pool of RAM, so the model's "VRAM" comes out of system memory.
- **Lockfile (`uv.lock`)**: Records the exact versions and hashes of all transitive dependencies for reproducible installs.
- **Dependency group**: A named set of dependencies (e.g. `dev`) in `pyproject.toml` (PEP 735) that is not part of the published package.
- **Liveness vs readiness probe**: Liveness asks "is the process running?" Readiness asks "can it serve traffic?" (e.g. are its dependencies reachable?).
- **12-factor config**: Keeping configuration in environment variables, separate from code, so the same build runs in any environment.
- **Structured output**: LLM output that conforms to a predefined schema (here, JSON matching a Pydantic model).
- **Constrained (grammar-guided) decoding**: Masking, at each generation step, every token that would break a grammar compiled from the schema, so the output is valid by construction.
- **Logits**: The model's raw, unnormalised scores for every vocabulary token at a generation step. Softmax turns them into probabilities.
- **Autoregressive generation**: Producing one token at a time, each conditioned on all the tokens before it. This is why field order in the schema matters.
- **JSON mode**: Constraining output to syntactically valid JSON without enforcing a particular schema.
- **Evidence span**: The verbatim text in the note that supports a flag. It is checked against the source to detect hallucination.
- **Risk taxonomy**: The closed set of risk categories the system may assign.
- **Pseudonymisation**: Replacing direct identifiers with references (e.g. `CL-0001`). Still personal data under UK GDPR, because re-identification is possible with the lookup key.
