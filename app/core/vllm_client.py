import httpx
import asyncio
import json
from typing import AsyncGenerator, Dict, Any, List
from loguru import logger
from app.config import settings

class VLLMClient:
    def __init__(self, base_url: str, model_name: str):
        self.base_url = base_url
        self.model_name = model_name
        self.limits = httpx.Limits(max_keepalive_connections=50, max_connections=100)
        self.client = httpx.AsyncClient(base_url=self.base_url, limits=self.limits, timeout=60.0)
        
    async def close(self) -> None:
        await self.client.aclose()

    async def check_health(self) -> bool:
        """Check if the vLLM server is healthy."""
        try:
            response = await self.client.get("/models", timeout=5.0)
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"vLLM health check failed: {e}")
            return False

    async def _retry_request(self, method: str, endpoint: str, **kwargs: Any) -> httpx.Response:
        max_retries = 3
        base_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                response = await self.client.request(method, endpoint, **kwargs)
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as e:
                if e.response.status_code in [429, 500, 502, 503, 504]:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"vLLM request failed with {e.response.status_code}, retrying in {delay}s...")
                    await asyncio.sleep(delay)
                else:
                    raise
            except httpx.RequestError as e:
                delay = base_delay * (2 ** attempt)
                logger.warning(f"vLLM connection error: {e}, retrying in {delay}s...")
                await asyncio.sleep(delay)
                
        raise Exception("Max retries exceeded for vLLM request")

    async def chat_completion(self, messages: List[Dict[str, str]], max_tokens: int = 512, temperature: float = 0.7) -> str:
        """Generate a complete chat completion (non-streaming)."""
        payload = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False
        }
        
        response = await self._retry_request("POST", "/chat/completions", json=payload)
        data = response.json()
        return data["choices"][0]["message"]["content"]

    async def chat_completion_stream(self, messages: List[Dict[str, str]], max_tokens: int = 512, temperature: float = 0.7) -> AsyncGenerator[str, None]:
        """Generate chat completion streaming tokens via AsyncGenerator."""
        payload = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True
        }
        
        try:
            async with self.client.stream("POST", "/chat/completions", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            if "choices" in data and len(data["choices"]) > 0:
                                delta = data["choices"][0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    yield content
                        except json.JSONDecodeError:
                            logger.error(f"Failed to parse JSON streaming line: {line}")
        except Exception as e:
            logger.error(f"Streaming failed: {e}")
            raise

vllm_client = VLLMClient(base_url=settings.vllm_base_url, model_name=settings.vllm_model_name)
