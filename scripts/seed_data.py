import os
import sys
import requests
import json
from datetime import datetime

API_URL = os.getenv("API_URL", "http://localhost:8080")

METADATA_MAPPING = {
    "employee_handbook.txt": {
        "department": "human_resources",
        "classification_level": 1,
        "author": "HR Department",
    },
    "it_security_policy.txt": {
        "department": "security_engineering",
        "classification_level": 2,
        "author": "Security Team",
    },
    "financial_reimbursement.txt": {
        "department": "finance",
        "classification_level": 1,
        "author": "Finance Department",
    },
}


def seed_documents():
    data_dir = os.path.join(os.path.dirname(__file__), "..", "data", "sample_documents")
    if not os.path.exists(data_dir):
        print(f"❌ Directory not found: {data_dir}")
        sys.exit(1)

    print("==========================================================")
    print("🌱 Enterprise RAG Data Seeder")
    print(f"   Target Gateway: {API_URL}")
    print("==========================================================")

    total_files = 0
    total_chunks = 0

    for filename in sorted(os.listdir(data_dir)):
        if not filename.endswith(".txt"):
            continue

        filepath = os.path.join(data_dir, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        meta = METADATA_MAPPING.get(filename, {
            "department": "general",
            "classification_level": 1,
            "author": "System",
        })
        # Build full metadata payload (all fields now optional in schema,
        # but we include everything for completeness)
        full_meta = {
            "source_file": filename,
            "department": meta["department"],
            "classification_level": meta["classification_level"],
            "author": meta["author"],
            "created_at": datetime.utcnow().isoformat(),
        }

        payload = {
            "raw_texts": [content],
            "metadata": full_meta,
        }

        try:
            resp = requests.post(
                f"{API_URL}/api/v1/ingest",
                json=payload,
                timeout=60,
            )
            if resp.status_code == 200:
                data = resp.json()
                # API returns total_chunks (not chunks_ingested)
                n_chunks = data.get("total_chunks", data.get("chunks_ingested", "?"))
                print(f"  ✅ '{filename}' → {n_chunks} chunks indexed into Qdrant")
                total_chunks += n_chunks if isinstance(n_chunks, int) else 0
                total_files += 1
            else:
                print(f"  ❌ Failed '{filename}': HTTP {resp.status_code} — {resp.text[:200]}")
        except requests.exceptions.ConnectionError:
            print(f"  ⚠️  Cannot connect to {API_URL}. Is the FastAPI server running?")
            sys.exit(1)
        except Exception as e:
            print(f"  ⚠️  Error ingesting '{filename}': {e}")

    print("----------------------------------------------------------")
    print(f"🎉 Seeding Complete!")
    print(f"   Files Ingested : {total_files}")
    print(f"   Total Chunks   : {total_chunks}")
    print("==========================================================")


if __name__ == "__main__":
    seed_documents()
