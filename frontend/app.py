import streamlit as st
import requests
import json
import os

# Configuration
API_URL = os.getenv("API_URL", "http://api-gateway:8080")

st.set_page_config(
    page_title="Enterprise RAG Assistant",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🤖 Enterprise RAG Assistant")
st.markdown("Powered by **vLLM (Qwen 2.5)**, **Qdrant**, and **Redis** Semantic Cache.")

# Session state initialization
if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_metrics" not in st.session_state:
    st.session_state.last_metrics = None
if "last_sources" not in st.session_state:
    st.session_state.last_sources = None

# Sidebar for Metrics & Sources
with st.sidebar:
    st.header("⚡ System Metrics")
    if st.session_state.last_metrics:
        metrics = st.session_state.last_metrics
        
        st.metric(
            label="Cache Status", 
            value="HIT (Redis)" if metrics.get("cache_hit") else "MISS (vLLM)",
            delta="Fast" if metrics.get("cache_hit") else "Processing"
        )
        st.metric(
            label="Total Latency", 
            value=f"{metrics.get('latency_ms', 0):.2f} ms"
        )
    else:
        st.info("No queries executed yet.")

    st.divider()
    st.header("📚 Retrieved Context")
    if st.session_state.last_sources:
        for idx, source in enumerate(st.session_state.last_sources):
            with st.expander(f"Source {idx + 1}"):
                st.write(source.get("text", ""))
                st.caption(f"Score: {source.get('score', 0):.4f}")
    else:
        st.info("No context retrieved yet.")

# Chat Interface
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Ask about your documents..."):
    # 1. Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2. Assistant response
    with st.chat_message("assistant"):
        # We'll use the sync query endpoint to easily capture the full response JSON including sources
        # Streaming in Streamlit with custom JSON chunks requires a bit more parsing, 
        # so for this demo, we'll use the robust /query endpoint.
        
        with st.spinner("Retrieving & Generating..."):
            try:
                payload = {"user_query": prompt}
                response = requests.post(f"{API_URL}/api/v1/query", json=payload)
                response.raise_for_status()
                
                data = response.json()
                answer = data.get("answer", "No answer generated.")
                sources = data.get("sources", [])
                
                # Update metrics
                st.session_state.last_metrics = {
                    "cache_hit": data.get("cache_hit", False),
                    "latency_ms": data.get("latency_ms", 0)
                }
                st.session_state.last_sources = sources
                
                st.markdown(answer)
                st.session_state.messages.append({"role": "assistant", "content": answer})
                
                # Rerun to update sidebar
                st.rerun()
                
            except Exception as e:
                st.error(f"Error communicating with backend API: {str(e)}")
