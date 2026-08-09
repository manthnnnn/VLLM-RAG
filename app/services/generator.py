import json
import asyncio
from typing import List, Dict, Any, AsyncGenerator
from loguru import logger
from app.models.schemas import RetrievedChunk
from app.core.vllm_client import vllm_client
from app.config import settings

# Demo answers for when vLLM is unavailable (DEMO_MODE=true)
DEMO_ANSWERS: Dict[str, str] = {
    "ssh": """**SSH Key Rotation Policy**

According to our security protocols, SSH keys must be rotated every **90 days** for all production systems.

**Key requirements:**
- All SSH keys must be 4096-bit RSA or Ed25519
- Keys must be stored in the central secrets vault (HashiCorp Vault)
- Rotation must be triggered via the IT Portal and logged in the SIEM system
- Unused keys older than 30 days are automatically revoked
- Service accounts require manual approval from the Security team for rotation

*Source: Security Policy Manual v3.2, Section 4.1 - SSH Key Management*""",

    "leave": """**Annual Leave Policy**

Employees are entitled to the following annual leave based on their employment tier:

| Level | Annual Leave Days |
|-------|------------------|
| Junior (0–2 years) | 15 days |
| Mid-level (2–5 years) | 18 days |
| Senior (5+ years) | 22 days |
| Manager | 25 days |

**Additional Notes:**
- Carry-forward limit: Maximum 5 days into next year
- Leave encashment: Available at year-end for unused days (capped at 10)
- Sick leave: Separate 12 days per year, non-encashable
- Maternity/Paternity leave: 26 weeks / 15 days respectively

*Source: HR Policy Handbook 2024, Section 6 - Leave Entitlements*""",

    "refund": """**Software Subscription Refund Policy**

Software subscription refund requests must be submitted within **30 days** of purchase.

**Refund Eligibility:**
- Full refund: Within 7 days, no questions asked
- Partial refund (50%): 8–30 days, requires manager approval
- No refund: After 30 days or if software has been deployed to production

**Process:**
1. Raise a ticket in ServiceNow under Category: *Finance > Procurement Refunds*
2. Attach the purchase order and invoice
3. Manager approval required for amounts > ₹5,000
4. Finance processes refunds within 10 business days

*Source: Finance SOP v2.1, Section 3.4 - Software Procurement*""",

    "home office": """**Home Office Setup Stipend**

New hires are eligible for a **₹25,000 one-time home office setup stipend** within the first 60 days of joining.

**Covered Items:**
- Ergonomic chair and desk accessories: Up to ₹12,000
- Monitor / display equipment: Up to ₹8,000
- Keyboard, mouse, and peripherals: Up to ₹3,000
- Internet upgrade or UPS: Up to ₹2,000

**Claim Process:**
1. Submit receipts via the HR Portal → Benefits → Home Office Claim
2. Attach proof of purchase within 30 days of purchase
3. Reimbursement credited to salary in the next payroll cycle

*Source: New Hire Benefits Guide 2024, Section 2 - Home Office Allowance*""",
}

def _get_demo_answer(query: str) -> str:
    """Return a context-aware demo answer based on query keywords."""
    q = query.lower()
    for keyword, answer in DEMO_ANSWERS.items():
        if keyword in q:
            return answer
    # Generic fallback answer
    return f"""**Enterprise AI Assistant Response** *(Demo Mode)*

Your question: *"{query}"*

Based on the enterprise knowledge base, I can provide the following information:

This system has indexed **internal policy documents** across departments including HR & Operations, IT Security, Finance, and Compliance. 

To get a specific answer, please ensure:
1. The relevant policy document has been ingested via the **Document Ingestion** panel on the left
2. The vLLM inference engine is running (for production answers)

**Currently Available Demo Topics:**
- 🔐 SSH key rotation & security policies
- 🏖️ Annual leave & HR entitlements  
- 💰 Software refund & procurement policies
- 🏠 Home office setup stipend

Try clicking one of the **Sample Questions** on the left panel for a full demo response.

*[Demo Mode Active — Connect vLLM for live AI generation]*"""

class RAGGenerator:
    def __init__(self):
        self.demo_mode = settings.demo_mode
        self.system_prompt_template = """You are an Enterprise AI Assistant.
Use the provided context to answer the user's question accurately and professionally.
If the answer is not contained in the context, state that you do not have enough information.
Do not hallucinate or make up information.

Context Information:
{context_str}

Always cite your sources by mentioning the source file and page number if available.
"""

    def _build_context_string(self, chunks: List[RetrievedChunk]) -> str:
        context_parts = []
        for i, chunk in enumerate(chunks):
            source = chunk.source_file
            page = chunk.page_number
            ref = f"[Source: {source}, Page: {page}]" if page else f"[Source: {source}]"
            context_parts.append(f"--- Document {i+1} {ref} ---\n{chunk.text}")
        return "\n\n".join(context_parts)

    def _build_messages(self, query: str, chunks: List[RetrievedChunk]) -> List[Dict[str, str]]:
        context_str = self._build_context_string(chunks)
        system_msg = self.system_prompt_template.format(context_str=context_str)
        
        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": query}
        ]
        return messages

    def _format_sources(self, chunks: List[RetrievedChunk]) -> List[Dict[str, Any]]:
        sources = []
        for chunk in chunks:
            sources.append({
                "chunk_id": chunk.chunk_id,
                "source_file": chunk.source_file,
                "page_number": chunk.page_number,
                "score": chunk.score
            })
        return sources

    async def generate_response(self, query: str, chunks: List[RetrievedChunk]) -> Dict[str, Any]:
        """Generate a complete text response."""
        # Try vLLM first; if unavailable and demo mode enabled, use demo answers
        if self.demo_mode:
            vllm_healthy = await vllm_client.check_health()
            if not vllm_healthy:
                logger.info("Demo mode: vLLM unreachable, returning demo answer.")
                await asyncio.sleep(0.8)  # Simulate latency
                return {
                    "answer": _get_demo_answer(query),
                    "sources": self._format_sources(chunks) if chunks else [
                        {"chunk_id": "demo-1", "source_file": "hr_policy_2024.pdf", "page_number": 6, "score": 0.94},
                        {"chunk_id": "demo-2", "source_file": "security_manual_v3.pdf", "page_number": 12, "score": 0.87},
                    ]
                }

        messages = self._build_messages(query, chunks)
        logger.info("Sending non-streaming request to vLLM.")
        
        try:
            response_text = await vllm_client.chat_completion(
                messages=messages,
                max_tokens=1024,
                temperature=0.3
            )
        except Exception as e:
            if self.demo_mode:
                logger.warning(f"vLLM error, falling back to demo: {e}")
                return {
                    "answer": _get_demo_answer(query),
                    "sources": self._format_sources(chunks)
                }
            raise
        
        return {
            "answer": response_text,
            "sources": self._format_sources(chunks)
        }

    async def generate_stream(self, query: str, chunks: List[RetrievedChunk]) -> AsyncGenerator[str, None]:
        """Generate streaming response using Server-Sent Events (SSE) format."""
        sources = self._format_sources(chunks) if chunks else [
            {"chunk_id": "demo-1", "source_file": "hr_policy_2024.pdf", "page_number": 6, "score": 0.94},
            {"chunk_id": "demo-2", "source_file": "security_manual_v3.pdf", "page_number": 12, "score": 0.88},
        ]

        # Check vLLM availability
        if self.demo_mode:
            vllm_healthy = await vllm_client.check_health()
            if not vllm_healthy:
                logger.info("Demo mode streaming: vLLM unreachable, streaming demo answer.")
                yield f"data: {json.dumps({'sources': sources})}\n\n"
                
                # Stream the demo answer token by token
                demo_answer = _get_demo_answer(query)
                words = demo_answer.split(" ")
                for i, word in enumerate(words):
                    token = word + (" " if i < len(words) - 1 else "")
                    yield f"data: {json.dumps({'token': token})}\n\n"
                    await asyncio.sleep(0.03)  # Simulate streaming speed
                
                yield "data: [DONE]\n\n"
                return

        messages = self._build_messages(query, chunks)
        logger.info("Sending streaming request to vLLM.")
        
        yield f"data: {json.dumps({'sources': sources})}\n\n"
        
        try:
            async for token in vllm_client.chat_completion_stream(
                messages=messages,
                max_tokens=1024,
                temperature=0.3
            ):
                data_payload = json.dumps({"token": token})
                yield f"data: {data_payload}\n\n"
        except Exception as e:
            if self.demo_mode:
                logger.warning(f"vLLM streaming error, falling back to demo: {e}")
                demo_answer = _get_demo_answer(query)
                words = demo_answer.split(" ")
                for i, word in enumerate(words):
                    token = word + (" " if i < len(words) - 1 else "")
                    yield f"data: {json.dumps({'token': token})}\n\n"
                    await asyncio.sleep(0.03)
            else:
                raise
            
        yield "data: [DONE]\n\n"

rag_generator = RAGGenerator()
