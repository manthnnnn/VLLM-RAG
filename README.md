

https://github.com/user-attachments/assets/263917d8-cd22-4679-81a1-d5fe9b71150f

# Enterprise Private Document Intelligence Engine

This project is an Enterprise Private Document Intelligence Engine. It allows an organization to upload internal company documents—such as policy manuals, technical specifications, legal contracts, and operational guidelines—and ask questions in natural language. The system retrieves exact information from those files and generates accurate answers in real time, with sources cited.

The system is designed with two fundamental architectural principles:
- **Zero Third-Party AI Dependencies:** It operates completely offline and on-premises without relying on external APIs like OpenAI, Anthropic, or Google. This guarantees total data privacy, eliminates per-token API costs, and prevents sensitive company information from leaving the infrastructure.
- **Sub-Second Real-Time Performance:** By integrating a custom inference framework, multi-vector search database, and semantic caching layer, the platform answers questions within milliseconds while streaming responses back word-by-word.

## Core Architectural Components

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                            FASTAPI API GATEWAY                              │
│         (Handles Security, PII Redaction & Prompt Injection Defense)        │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       REDIS SEMANTIC CACHE LAYER                            │
│           (Intercepts repeated queries & returns answers in <10ms)          │
└───────────────────────┬───────────────────────────────┬─────────────────────┘
                        │                               │
              (Cache Hit: <10ms)                  (Cache Miss)
                        │                               │
                        ▼                               ▼
             [Return Cached Answer]     ┌─────────────────────────────────────┐
                                        │   QDRANT HYBRID RETRIEVAL ENGINE    │
                                        │   - Dense Semantic Search (BGE)     │
                                        │   - Sparse Keyword Search (BM25)    │
                                        │   - RBAC Payload Security Filters   │
                                        └──────────────────┬──────────────────┘
                                                           │
                                                           ▼
                                        ┌─────────────────────────────────────┐
                                        │      SELF-HOSTED vLLM ENGINE        │
                                        │    (PagedAttention & 4-Bit AWQ)     │
                                        └──────────────────┬──────────────────┘
                                                           │
                                                           ▼
                                        ┌─────────────────────────────────────┐
                                        │   Real-Time Word-by-Word SSE Stream │
                                        └─────────────────────────────────────┘
```

*Note: A Streamlit UI (Frontend) connects to the API Gateway for an interactive user experience.*

### 1. High-Throughput Inference Engine (vLLM)
At the core of the generation layer is **vLLM**, an open-source inference and serving engine designed for Large Language Models.
- **PagedAttention:** Traditional LLMs waste up to 60–80% of GPU memory storing Key-Value (KV) cache states. PagedAttention manages KV memory using virtual memory allocation algorithms similar to operating systems, reducing memory fragmentation to near 0%.
- **Quantization (AWQ 4-bit):** The hosted model (Qwen 2.5 7B) is compressed using Activation-aware Weight Quantization. This reduces GPU memory consumption from 14 GB down to under 5 GB while maintaining high accuracy, allowing a standard single GPU to process dozens of parallel user requests at speeds over 50 tokens per second.

### 2. Storage & Retrieval Engine (Qdrant Vector Database)
To locate relevant information across thousands of pages, the system uses **Qdrant** configured with a Hybrid Retrieval Mechanism:
- **Dense Vectors (BAAI/bge-small-en-v1.5):** Converts sentences into 384-dimensional mathematical vectors to capture semantic meaning, context, and synonyms (e.g., matching "reimbursement" with "refund").
- **Sparse Vectors (BM25):** Captures exact lexical matches, such as policy IDs, technical codes, product SKU numbers, or specific names.
- **Reciprocal Rank Fusion (RRF):** Blends dense semantic search results with sparse keyword matches to ensure high context precision.
- **Role-Based Access Control (RBAC):** Every document chunk stored in Qdrant retains metadata attributes (department and classification_level). At search time, Qdrant applies security payload filters, preventing unauthorized users from accessing confidential documents above their clearance level.

### 3. Speed Acceleration Layer (Redis Semantic Caching)
To minimize GPU computation overhead, the system incorporates an asynchronous **Redis Semantic Vector Cache**:
- Instead of checking for identical string matches, Redis embeds incoming user queries and checks historical questions using vector similarity.
- If a new query matches a previous question above a 92% semantic similarity threshold, the answer is returned directly from Redis in under 10 milliseconds, bypassing both vector search and LLM inference.

### 4. Asynchronous Processing & Security Pipeline (FastAPI & Guardrails)
- **Document Processing:** Ingested files (PDFs, Markdown, text) are asynchronously parsed, recursively split into 512-character chunks with a 64-character overlap to preserve sentence boundaries, and indexed into Qdrant.
- **Input Guardrails:** An input sanitization module inspects incoming prompts for system prompt injections, jailbreak attempts, and sensitive information before sending queries to the vector database or LLM.
- **Streaming Generation:** Using Server-Sent Events (SSE), the system streams tokens word-by-word to the client interface, achieving a Time to First Token (TTFT) of under 200 milliseconds.

## Technical Metrics Summary

| Feature | Technical Implementation | Performance Impact |
| :--- | :--- | :--- |
| **Model Serving** | vLLM + AWQ 4-bit Quantization | >50 tokens/second generation throughput |
| **Vector Indexing** | Qdrant Hybrid (BGE Dense + BM25 Sparse) | Context retrieval latency <35ms |
| **Caching Engine** | Redis Semantic Vector Match (>0.92) | Sub-10ms response time on cache hits |
| **Response Delivery** | FastAPI Server-Sent Events (SSE) | Time to First Token (TTFT) <200ms |
| **Security Layer** | RBAC Metadata Filtering & Prompt Guardrails | Complete data isolation & clearance enforcement |

---

## Operational Guide

### Step 1: Boot the Infrastructure
Start the background services (Qdrant, Redis, FastAPI Gateway, Streamlit UI) using Docker Compose:
```bash
docker-compose up -d --build
```
Check that all containers are healthy:
```bash
docker-compose ps
```

### Step 2: Access the Frontend UI
Once the containers are running, you can access the beautiful Streamlit chat interface at:
**[http://localhost:8501](http://localhost:8501)**

### Step 3: Launch the vLLM Inference Engine
If vLLM is running on your host machine or GPU instance (outside Docker), execute the boot script:
```bash
chmod +x scripts/start_vllm.sh
./scripts/start_vllm.sh
```
Verify that vLLM is listening on port 8000:
```bash
curl http://localhost:8000/v1/models
```

### Step 4: Seed Data & Run Automated Synthetic RAG Evaluation

**1. Seed Enterprise Sample Datasets:** Populate Qdrant vector index with internal policies (Employee Handbook, IT Security, Financial Reimbursements):
```bash
python scripts/seed_data.py
```

**2. Run Synthetic RAG Evaluation:** Evaluate retrieval precision, answer accuracy, and Redis semantic cache hit speed:
```bash
python scripts/eval_rag.py
```

**3. Execute Load & Throughput Benchmark:** Test concurrent async throughput and TTFT:
```bash
python scripts/benchmark.py
```

https://github.com/user-attachments/assets/9f10bf18-7a8b-43d3-9b56-6fa43279de7f


