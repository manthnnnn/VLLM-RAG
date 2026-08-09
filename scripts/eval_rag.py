import os
import sys
import time
import requests
import json
from tabulate import tabulate

API_URL = os.getenv("API_URL", "http://localhost:8080")

EVAL_DATASET = [
    {
        "id": 1,
        "question": "How many annual leaves do employees get and how many can be carried forward?",
        "expected_keywords": ["22 paid annual leaves", "5 days"],
        "expected_source": "employee_handbook.txt"
    },
    {
        "id": 2,
        "question": "What is the policy for SSH key rotation and production server access?",
        "expected_keywords": ["90 days", "Teleport Bastion"],
        "expected_source": "it_security_policy.txt"
    },
    {
        "id": 3,
        "question": "Within how many days can software subscriptions be refunded?",
        "expected_keywords": ["14 days", "manager approval"],
        "expected_source": "financial_reimbursement.txt"
    },
    {
        "id": 4,
        "question": "What is the home office allowance stipend for new hires?",
        "expected_keywords": ["$500", "home office"],
        "expected_source": "employee_handbook.txt"
    },
    {
        "id": 5,
        "question": "What is the per diem meal allowance for travel in high-cost cities like SF?",
        "expected_keywords": ["$100 per day", "San Francisco"],
        "expected_source": "financial_reimbursement.txt"
    }
]

def run_rag_eval():
    print("==========================================================")
    print("🧪 Synthetic RAG System Evaluation & Benchmarking")
    print(f"Target Gateway: {API_URL}")
    print("==========================================================")

    results = []

    for item in EVAL_DATASET:
        qid = item["id"]
        q = item["question"]
        expected_kw = item["expected_keywords"]

        # Run 1: Cold Query (Cache MISS expected or initial run)
        t0 = time.time()
        try:
            res1 = requests.post(f"{API_URL}/api/v1/query", json={"user_query": q}, timeout=30).json()
            cold_latency = (time.time() - t0) * 1000.0
            answer1 = res1.get("answer", "")
            sources1 = res1.get("sources", [])
            cache1 = res1.get("cache_hit", False)
        except Exception as e:
            print(f"❌ Error querying Q{qid}: {e}")
            continue

        # Check retrieval precision
        retrieved_texts = " ".join([s.get("text", "") for s in sources1])
        retrieval_hit = any(kw.lower() in retrieved_texts.lower() for kw in expected_kw)

        # Check answer completeness
        answer_hit = any(kw.lower() in answer1.lower() for kw in expected_kw)

        # Run 2: Immediate Repeated Query (Redis Cache HIT expected)
        t1 = time.time()
        try:
            res2 = requests.post(f"{API_URL}/api/v1/query", json={"user_query": q}, timeout=30).json()
            warm_latency = (time.time() - t1) * 1000.0
            cache2 = res2.get("cache_hit", False)
        except Exception:
            warm_latency = 0
            cache2 = False

        results.append({
            "id": qid,
            "question": q[:40] + "...",
            "retrieval_pass": "✅ PASS" if retrieval_hit else "❌ FAIL",
            "generation_pass": "✅ PASS" if answer_hit else "❌ FAIL",
            "cold_ms": f"{cold_latency:.1f}ms",
            "warm_ms": f"{warm_latency:.1f}ms",
            "cache_hit": "⚡ HIT" if cache2 else "MISS"
        })

    print("\n📊 EVALUATION METRICS TABLE:")
    headers = ["ID", "Question", "Retrieval Precision", "Answer Accuracy", "Cold Latency", "Warm Latency", "Redis Cache"]
    rows = [
        [r["id"], r["question"], r["retrieval_pass"], r["generation_pass"], r["cold_ms"], r["warm_ms"], r["cache_hit"]]
        for r in results
    ]
    print(tabulate(rows, headers=headers, tablefmt="github"))

    print("\n----------------------------------------------------------")
    retrieval_acc = (sum(1 for r in results if r["retrieval_pass"] == "✅ PASS") / len(results)) * 100.0
    generation_acc = (sum(1 for r in results if r["generation_pass"] == "✅ PASS") / len(results)) * 100.0
    print(f"🎯 Retrieval Context Accuracy: {retrieval_acc:.1f}%")
    print(f"🤖 Answer Generation Accuracy: {generation_acc:.1f}%")
    print("==========================================================")

if __name__ == "__main__":
    run_rag_eval()
