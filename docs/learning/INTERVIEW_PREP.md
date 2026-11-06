# Interview Prep: Cumulative Q&A bank

## Setup / Infrastructure

**Why run the LLM locally rather than call a hosted API?**
Care notes are special-category health data under UK GDPR (Article 9). A hosted API makes the provider a processor, which brings contracts, transfer checks and a broader DPIA. Local inference keeps data on infrastructure PBL controls. The trade-off is lower model quality and running the model ourselves. That is acceptable for narrow extraction that is human-reviewed and evaluated against a baseline.

**How did you choose the model size?**
I matched it to the hardware: 16 GB of unified memory fits an 8B model at Q4 (~4.9 GB). A 3B model is also pulled, so Step 1.9 measures the quality-versus-latency trade-off instead of asserting it.

**What is quantisation and what does it cost you?**
Fewer bits per weight (e.g. 4-bit with block scales) means about 4× less memory and faster, bandwidth-bound inference. The cost is a small accuracy loss, which may show up in negation handling. That's why negated cases are in the eval set.

**Why pin Python 3.12 when 3.14 was available?**
The spaCy and Presidio wheels lag new Python releases. Pinning prevents a broken install halfway through the build. The pin is enforced by `.python-version` and `requires-python`.

**With real PBL data and at scale, what changes?**
A dedicated inference server inside PBL's network (or vLLM on a GPU), with auth and TLS. Managed, encrypted Postgres. A secrets manager. Readiness probes. The architecture stays the same.

**Trade-off: why not containerise Ollama too?**
Docker on macOS has no Metal GPU, so the model would run CPU-only and distort the latency results. I chose correct performance over one-command setup. On a Linux GPU server I would containerise it.
