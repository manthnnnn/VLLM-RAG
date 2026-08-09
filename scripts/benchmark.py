import asyncio
import time
import statistics
import httpx
from typing import List, Dict, Any

API_URL = "http://localhost:8080/api/v1"
TEST_QUERY = {
    "user_query": "What are the key security features of this system?",
    "user_role": "admin",
    "user_department": "engineering",
    "top_k": 3,
    "alpha": 0.5
}

async def send_sync_query(client: httpx.AsyncClient) -> Dict[str, Any]:
    start_time = time.time()
    try:
        response = await client.post(f"{API_URL}/query", json=TEST_QUERY, timeout=30.0)
        response.raise_for_status()
        end_time = time.time()
        return {
            "latency": end_time - start_time,
            "status": response.status_code,
            "cache_hit": response.json().get("cache_hit", False)
        }
    except Exception as e:
        print(f"Sync Request failed: {e}")
        return {"latency": 0.0, "status": 500, "cache_hit": False}

async def send_stream_query(client: httpx.AsyncClient) -> Dict[str, Any]:
    start_time = time.time()
    ttft = 0.0
    tokens = 0
    
    try:
        async with client.stream("POST", f"{API_URL}/stream", json=TEST_QUERY, timeout=30.0) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    
                    if ttft == 0.0 and '"token"' in data_str:
                        ttft = time.time() - start_time
                    
                    if '"token"' in data_str:
                        tokens += 1
                        
        end_time = time.time()
        total_time = end_time - start_time
        tok_sec = tokens / total_time if total_time > 0 else 0
        
        return {
            "ttft": ttft,
            "tok_sec": tok_sec,
            "total_time": total_time,
            "status": response.status_code
        }
    except Exception as e:
        print(f"Stream Request failed: {e}")
        return {"ttft": 0.0, "tok_sec": 0.0, "total_time": 0.0, "status": 500}

async def run_benchmark(concurrent_users: int = 20, is_stream: bool = False):
    print(f"\n--- Starting Benchmark: {concurrent_users} Concurrent Users | Streaming: {is_stream} ---")
    
    async with httpx.AsyncClient() as client:
        # Warmup cache
        if not is_stream:
            print("Warming up cache...")
            await send_sync_query(client)
        
        tasks = []
        for _ in range(concurrent_users):
            if is_stream:
                tasks.append(send_stream_query(client))
            else:
                tasks.append(send_sync_query(client))
                
        start_time = time.time()
        results = await asyncio.gather(*tasks)
        total_time = time.time() - start_time
        
        successes = [r for r in results if r["status"] == 200]
        
        if is_stream:
            ttfts = [r["ttft"] for r in successes if r["ttft"] > 0]
            tok_secs = [r["tok_sec"] for r in successes if r["tok_sec"] > 0]
            latencies = [r["total_time"] for r in successes]
            
            print(f"Total Requests: {concurrent_users} | Successful: {len(successes)}")
            print(f"Avg TTFT: {statistics.mean(ttfts):.3f}s" if ttfts else "Avg TTFT: N/A")
            print(f"Avg Tok/Sec: {statistics.mean(tok_secs):.2f}" if tok_secs else "Avg Tok/Sec: N/A")
            
        else:
            latencies = [r["latency"] for r in successes]
            cache_hits = sum(1 for r in successes if r["cache_hit"])
            
            print(f"Total Requests: {concurrent_users} | Successful: {len(successes)}")
            print(f"Cache Hits: {cache_hits}")
            
        if latencies:
            print(f"P50 Latency: {statistics.quantiles(latencies, n=100)[49]:.3f}s")
            print(f"P90 Latency: {statistics.quantiles(latencies, n=100)[89]:.3f}s")
            print(f"P95 Latency: {statistics.quantiles(latencies, n=100)[94]:.3f}s")

if __name__ == "__main__":
    asyncio.run(run_benchmark(concurrent_users=20, is_stream=False))
    asyncio.run(run_benchmark(concurrent_users=20, is_stream=True))
