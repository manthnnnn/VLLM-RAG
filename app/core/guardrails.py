import re
from typing import Dict, Any
from fastapi import HTTPException, status
from loguru import logger

class GuardrailsService:
    def __init__(self):
        # Basic patterns for prompt injection attempts
        self.injection_patterns = [
            re.compile(r"(?i)ignore\s+(all\s+)?(previous\s+)?instructions"),
            re.compile(r"(?i)system\s+prompt"),
            re.compile(r"(?i)dan\s+mode"),
            re.compile(r"(?i)jailbreak"),
            re.compile(r"(?i)forget\s+(all\s+)?rules")
        ]
        
        # PII and Secrets patterns
        self.pii_patterns = [
            # Credit Card (basic approximation)
            (re.compile(r"\b(?:\d[ -]*?){13,16}\b"), "[REDACTED_CC]"),
            # API Keys / Tokens (e.g., Bearer tokens, AWS keys)
            (re.compile(r"(?i)(bearer\s+[a-zA-Z0-9_\-\.]+)|(AKIA[0-9A-Z]{16})"), "[REDACTED_SECRET]"),
        ]

    async def sanitize_input(self, text: str) -> str:
        """Sanitize input text by redacting PII and secrets."""
        sanitized_text = text
        for pattern, replacement in self.pii_patterns:
            sanitized_text = pattern.sub(replacement, sanitized_text)
            
        if sanitized_text != text:
            logger.warning("PII or Secret redacted from input.")
            
        return sanitized_text

    async def check_prompt_injection(self, text: str) -> None:
        """Check for prompt injection attacks and raise exception if found."""
        for pattern in self.injection_patterns:
            if pattern.search(text):
                logger.error(f"Prompt injection attempt detected: {text[:100]}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Potentially malicious input detected. Request blocked."
                )

    async def audit_output(self, generated_text: str) -> str:
        """Verify the output doesn't contain sensitive system information."""
        # Check if the model accidentally leaked backend infrastructure details
        forbidden_terms = ["traceback", "redis://", "qdrant://", "Exception in"]
        
        for term in forbidden_terms:
            if term in generated_text:
                logger.error("Output audit failed: Sensitive infrastructure details leaked.")
                return "I apologize, but I cannot provide a response at this time due to an internal security policy."
                
        return generated_text

guardrails = GuardrailsService()
