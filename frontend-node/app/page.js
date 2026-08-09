"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import {
  Bot, User, Zap, Database, Shield, Cpu,
  Upload, FileText, CheckCircle2, AlertCircle, RefreshCw, Send, FileCheck,
  Sparkles, Clock, Layers, ChevronRight, HelpCircle, X, Info, BookOpen, Search,
  Trash2, UserCheck, Lock, ChevronDown, Activity, Server
} from "lucide-react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8081";

// ─── Markdown-lite renderer ────────────────────────────────────────────────────
function renderMarkdown(text) {
  const lines = text.split("\n");
  const elements = [];
  let listItems = [];
  let key = 0;

  const flushList = () => {
    if (listItems.length > 0) {
      elements.push(
        <ul key={key++} className="list-disc list-inside space-y-1 my-1">
          {listItems.map((li, i) => (
            <li key={i} className="text-slate-200">{li}</li>
          ))}
        </ul>
      );
      listItems = [];
    }
  };

  for (let i = 0; i < lines.length; i++) {
    let line = lines[i];

    // Bold + inline code
    line = line.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    line = line.replace(/`([^`]+)`/g, '<code class="bg-black/40 px-1 rounded text-indigo-300 font-mono text-[11px]">$1</code>');

    if (/^#{1,3}\s/.test(line)) {
      flushList();
      const content = line.replace(/^#{1,3}\s/, "");
      elements.push(
        <p key={key++} className="font-bold text-indigo-300 mt-2 mb-0.5"
          dangerouslySetInnerHTML={{ __html: content }} />
      );
    } else if (/^[-*]\s/.test(line)) {
      listItems.push(line.replace(/^[-*]\s/, "").trim());
    } else if (/^\d+\.\s/.test(line)) {
      flushList();
      elements.push(
        <p key={key++} className="text-slate-200 my-0.5"
          dangerouslySetInnerHTML={{ __html: line }} />
      );
    } else if (line.trim() === "") {
      flushList();
      elements.push(<div key={key++} className="h-1" />);
    } else {
      flushList();
      elements.push(
        <p key={key++} className="text-slate-200 leading-relaxed"
          dangerouslySetInnerHTML={{ __html: line }} />
      );
    }
  }
  flushList();
  return elements;
}

// ─── Role Config ───────────────────────────────────────────────────────────────
const ROLES = [
  { value: "admin",    label: "Admin",    dept: "general",            clearance: 5, color: "text-rose-300",    bg: "bg-rose-500/15",    border: "border-rose-500/30" },
  { value: "manager",  label: "Manager",  dept: "human_resources",    clearance: 3, color: "text-amber-300",   bg: "bg-amber-500/15",   border: "border-amber-500/30" },
  { value: "employee", label: "Employee", dept: "human_resources",    clearance: 2, color: "text-emerald-300", bg: "bg-emerald-500/15", border: "border-emerald-500/30" },
  { value: "guest",    label: "Guest",    dept: "general",            clearance: 1, color: "text-slate-300",   bg: "bg-slate-500/15",   border: "border-slate-500/30" },
];

const DEPARTMENTS = [
  { value: "general",              label: "All Departments" },
  { value: "human_resources",      label: "HR & Operations" },
  { value: "security_engineering", label: "Security & IT" },
  { value: "finance",              label: "Finance" },
  { value: "legal",                label: "Legal & Contracts" },
];

export default function Home() {
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content: "Welcome! I am your **Enterprise Document Intelligence Assistant**.\n\nAsk any question about uploaded internal policies, security protocols, or financial terms. I'll retrieve the most relevant chunks from Qdrant and generate an accurate answer.\n\n**Try a sample question** from the left panel to see the full pipeline in action!",
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    },
  ]);
  const [inputQuery, setInputQuery] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  // Metrics & Sources
  const [lastMetrics, setLastMetrics] = useState(null);
  const [lastSources, setLastSources] = useState([]);

  // Ingestion form
  const [ingestText, setIngestText] = useState("");
  const [ingestDept, setIngestDept] = useState("human_resources");
  const [ingestLevel, setIngestLevel] = useState(1);
  const [ingestStatus, setIngestStatus] = useState(null);
  const [isIngesting, setIsIngesting] = useState(false);

  // Role selector
  const [selectedRole, setSelectedRole] = useState(ROLES[2]); // default: employee
  const [selectedDept, setSelectedDept] = useState(DEPARTMENTS[1]);

  // Collection stats
  const [collectionStats, setCollectionStats] = useState(null);

  // Guide modal
  const [showGuideModal, setShowGuideModal] = useState(false);
  const [activeGuideStep, setActiveGuideStep] = useState(1);

  // Health
  const [healthStatus, setHealthStatus] = useState({ api: "checking", redis: "unknown", vllm: "unknown" });

  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    checkHealth();
    fetchStats();
    const interval = setInterval(checkHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  const checkHealth = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/health`);
      if (res.ok) {
        const data = await res.json();
        setHealthStatus({
          api: "healthy",
          redis: data.redis === "ok" ? "healthy" : "degraded",
          vllm: data.vllm === "ok" ? "healthy" : data.demo_mode === "true" ? "demo" : "offline",
        });
      } else {
        setHealthStatus({ api: "degraded", redis: "unknown", vllm: "unknown" });
      }
    } catch {
      setHealthStatus({ api: "offline", redis: "unknown", vllm: "unknown" });
    }
  };

  const fetchStats = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/stats`);
      if (res.ok) {
        const data = await res.json();
        setCollectionStats(data);
      }
    } catch {
      setCollectionStats(null);
    }
  };

  const handleSendQuery = useCallback(async (queryOverride) => {
    const query = queryOverride ?? inputQuery;
    if (!query.trim() || isLoading) return;

    const userMsg = {
      role: "user",
      content: query,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages((prev) => [...prev, userMsg]);
    if (!queryOverride) setInputQuery("");
    setIsLoading(true);

    const t0 = performance.now();

    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_query: query,
          user_role: selectedRole.value,
          user_department: selectedDept.value,
        }),
      });

      if (!res.ok) {
        const errText = await res.text();
        throw new Error(`HTTP ${res.status}: ${errText.slice(0, 200)}`);
      }

      const data = await res.json();
      const t1 = performance.now();

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.answer || "No answer generated.",
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        },
      ]);

      setLastMetrics({
        cacheHit: data.cache_hit || false,
        latencyMs: data.latency_ms ? Math.round(data.latency_ms) : Math.round(t1 - t0),
        retrievedChunks: (data.sources || []).length,
      });

      setLastSources(data.sources || []);

      // Refresh stats after query
      fetchStats();
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `⚠️ **Connection Error**\n\n${err.message}\n\nEnsure the FastAPI backend is running:\n\`uvicorn app.main:app --port 8080 --reload\``,
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        },
      ]);
    } finally {
      setIsLoading(false);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [inputQuery, isLoading, selectedRole, selectedDept]);

  const handleIngestDocument = async (e) => {
    e.preventDefault();
    if (!ingestText.trim() || isIngesting) return;

    setIsIngesting(true);
    setIngestStatus(null);

    try {
      const payload = {
        raw_texts: [ingestText],
        metadata: {
          source_file: `doc_${Date.now()}.txt`,
          department: ingestDept,
          classification_level: Number(ingestLevel),
          author: "User Upload",
        },
      };

      const res = await fetch(`${API_BASE_URL}/api/v1/ingest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.text();
        throw new Error(err.slice(0, 200));
      }

      const data = await res.json();
      const chunks = data.total_chunks ?? data.chunks_ingested ?? "?";
      setIngestStatus({ type: "success", msg: `✅ Indexed ${chunks} chunks into Qdrant!` });
      setIngestText("");
      fetchStats();
    } catch (err) {
      setIngestStatus({ type: "error", msg: `❌ ${err.message}` });
    } finally {
      setIsIngesting(false);
    }
  };

  const handleClearChat = () => {
    setMessages([{
      role: "assistant",
      content: "Chat cleared. Ask me anything about your enterprise documents!",
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    }]);
    setLastMetrics(null);
    setLastSources([]);
  };

  const sampleQuestions = [
    "What is the SSH key rotation policy?",
    "How many annual leaves do employees get?",
    "Within how many days can software subscriptions be refunded?",
    "What is the home office setup stipend for new hires?",
  ];

  const statusColor = (s) => {
    if (s === "healthy") return "bg-emerald-400";
    if (s === "demo") return "bg-amber-400";
    if (s === "degraded") return "bg-orange-400";
    return "bg-rose-400";
  };

  return (
    <div className="root-layout">

      {/* ── HEADER ─────────────────────────────────────────────────────────── */}
      <header className="header">
        <div className="header-brand">
          <div className="brand-icon">
            <Sparkles className="icon-sm pulse" />
          </div>
          <div>
            <h1 className="brand-title">
              Enterprise Document Intelligence
              <span className="badge-pill badge-indigo">DEMO</span>
            </h1>
            <p className="brand-sub">vLLM · Qdrant Hybrid · Redis Semantic Cache</p>
          </div>
        </div>

        <div className="header-actions">
          <button onClick={() => setShowGuideModal(true)} className="guide-btn">
            <HelpCircle className="icon-xs" />
            <span>Guide</span>
          </button>

          {/* Health Pills */}
          <div className="health-pills">
            {[
              { label: "API", key: "api" },
              { label: "Redis", key: "redis" },
              { label: "vLLM", key: "vllm" },
            ].map(({ label, key }) => (
              <div key={key} className="health-pill">
                <span className={`status-dot ${statusColor(healthStatus[key])}`} />
                <span className="text-slate-400">{label}</span>
                <span className="font-mono text-[11px] text-slate-200">{healthStatus[key]}</span>
              </div>
            ))}
          </div>
        </div>
      </header>

      {/* ── INFO BANNER ────────────────────────────────────────────────────── */}
      <div className="info-banner">
        <Info className="icon-xs text-indigo-400 shrink-0" />
        <span><strong>Quick Start:</strong> Paste policy text in the left panel → ingest → ask a question below. Ask the same question twice to see Redis cache hit in action!</span>
        <button onClick={() => setShowGuideModal(true)} className="banner-link">
          Full Guide →
        </button>
      </div>

      {/* ── MAIN 3-COLUMN LAYOUT ───────────────────────────────────────────── */}
      <div className="main-grid">

        {/* ── LEFT COLUMN ──────────────────────────────────────────────────── */}
        <aside className="col-left">

          {/* Role & Access Selector */}
          <div className="card">
            <div className="card-header">
              <div className="card-icon" style={{ background: "rgba(251,191,36,0.15)" }}>
                <UserCheck className="icon-sm text-amber-300" />
              </div>
              <h2 className="card-title">Access Context</h2>
              <span className="badge-pill badge-amber">RBAC</span>
            </div>

            <div className="field-group">
              <label className="field-label">Your Role</label>
              <div className="role-grid">
                {ROLES.map((role) => (
                  <button
                    key={role.value}
                    onClick={() => { setSelectedRole(role); setSelectedDept(DEPARTMENTS.find(d => d.value === role.dept) || DEPARTMENTS[0]); }}
                    className={`role-btn ${selectedRole.value === role.value ? `role-btn-active ${role.bg} ${role.border} ${role.color}` : "role-btn-inactive"}`}
                  >
                    {role.label}
                    {selectedRole.value === role.value && <span className="role-check">✓</span>}
                  </button>
                ))}
              </div>
            </div>

            <div className="field-group">
              <label className="field-label">Department Filter</label>
              <select
                value={selectedDept.value}
                onChange={(e) => setSelectedDept(DEPARTMENTS.find(d => d.value === e.target.value))}
                className="select-input"
              >
                {DEPARTMENTS.map((d) => (
                  <option key={d.value} value={d.value}>{d.label}</option>
                ))}
              </select>
            </div>

            <div className={`role-badge ${selectedRole.bg} ${selectedRole.border} ${selectedRole.color}`}>
              <Lock className="icon-xs" />
              <span>Clearance Level {selectedRole.clearance} · {selectedRole.label}</span>
            </div>
          </div>

          {/* Document Ingestion */}
          <div className="card">
            <div className="card-header">
              <div className="card-icon" style={{ background: "rgba(129,140,248,0.15)" }}>
                <Upload className="icon-sm text-indigo-300" />
              </div>
              <h2 className="card-title">Document Ingestion</h2>
              <span className="badge-pill badge-indigo">Qdrant</span>
            </div>

            <form onSubmit={handleIngestDocument} className="form-stack">
              <div className="field-group">
                <label className="field-label">Document Text</label>
                <textarea
                  value={ingestText}
                  onChange={(e) => setIngestText(e.target.value)}
                  placeholder="Paste policy manuals, SOPs, technical specs..."
                  rows={4}
                  className="textarea-input"
                />
              </div>

              <div className="field-row">
                <div className="field-group">
                  <label className="field-label">Department</label>
                  <select value={ingestDept} onChange={(e) => setIngestDept(e.target.value)} className="select-input">
                    {DEPARTMENTS.slice(1).map((d) => (
                      <option key={d.value} value={d.value}>{d.label}</option>
                    ))}
                  </select>
                </div>
                <div className="field-group">
                  <label className="field-label">Clearance</label>
                  <select value={ingestLevel} onChange={(e) => setIngestLevel(e.target.value)} className="select-input">
                    <option value={1}>L1: Internal</option>
                    <option value={2}>L2: Confidential</option>
                    <option value={3}>L3: Restricted</option>
                  </select>
                </div>
              </div>

              <button type="submit" disabled={isIngesting || !ingestText.trim()} className="btn-primary">
                {isIngesting ? <RefreshCw className="icon-sm spin" /> : <FileCheck className="icon-sm" />}
                {isIngesting ? "Indexing Chunks..." : "Ingest Document"}
              </button>
            </form>

            {ingestStatus && (
              <div className={`status-alert ${ingestStatus.type === "success" ? "status-success" : "status-error"}`}>
                {ingestStatus.type === "success"
                  ? <CheckCircle2 className="icon-xs shrink-0" />
                  : <AlertCircle className="icon-xs shrink-0" />}
                <span>{ingestStatus.msg}</span>
              </div>
            )}
          </div>

          {/* Sample Questions */}
          <div className="card">
            <div className="card-header-simple">
              <Sparkles className="icon-sm text-amber-300" />
              <h3 className="card-title">Sample Questions</h3>
            </div>
            <div className="questions-list">
              {sampleQuestions.map((q, idx) => (
                <button
                  key={idx}
                  onClick={() => handleSendQuery(q)}
                  disabled={isLoading}
                  className="question-btn"
                >
                  <span className="question-text">{q}</span>
                  <ChevronRight className="icon-xs text-slate-500 group-hover:text-indigo-300 shrink-0" />
                </button>
              ))}
            </div>
          </div>
        </aside>

        {/* ── CENTER COLUMN: CHAT ───────────────────────────────────────────── */}
        <main className="col-center">
          <div className="chat-header">
            <div className="chat-header-left">
              <span className="status-dot bg-emerald-400 pulse" />
              <span className="chat-title">Live Intelligence Stream</span>
            </div>
            <div className="chat-header-right">
              <span className="model-badge">Qwen 2.5 7B · Demo Mode</span>
              <button onClick={handleClearChat} className="clear-btn" title="Clear chat">
                <Trash2 className="icon-xs" />
              </button>
            </div>
          </div>

          {/* Messages */}
          <div className="messages-list">
            {messages.map((msg, idx) => (
              <div key={idx} className={`message-row ${msg.role === "user" ? "message-user" : ""}`}>
                <div className={`avatar ${msg.role === "user" ? "avatar-user" : "avatar-bot"}`}>
                  {msg.role === "user" ? <User className="icon-sm" /> : <Bot className="icon-sm" />}
                </div>
                <div className="message-body">
                  <div className={`bubble ${msg.role === "user" ? "bubble-user" : "bubble-bot"}`}>
                    {msg.role === "user"
                      ? <p>{msg.content}</p>
                      : <div className="markdown-body">{renderMarkdown(msg.content)}</div>
                    }
                  </div>
                  <span className={`timestamp ${msg.role === "user" ? "text-right" : "text-left"}`}>
                    {msg.timestamp}
                  </span>
                </div>
              </div>
            ))}

            {isLoading && (
              <div className="message-row">
                <div className="avatar avatar-bot">
                  <Bot className="icon-sm pulse" />
                </div>
                <div className="bubble bubble-bot typing-indicator">
                  <RefreshCw className="icon-sm spin text-indigo-400" />
                  <span>Searching Qdrant & generating with vLLM...</span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input Bar */}
          <div className="input-bar">
            <form
              onSubmit={(e) => { e.preventDefault(); handleSendQuery(); }}
              className="input-form"
            >
              <input
                ref={inputRef}
                type="text"
                value={inputQuery}
                onChange={(e) => setInputQuery(e.target.value)}
                placeholder="Ask about company policies, security guidelines, refund terms..."
                className="chat-input"
              />
              <button
                type="submit"
                disabled={isLoading || !inputQuery.trim()}
                className="send-btn"
              >
                <Send className="icon-sm" />
              </button>
            </form>
          </div>
        </main>

        {/* ── RIGHT COLUMN: METRICS ─────────────────────────────────────────── */}
        <aside className="col-right">

          {/* System Metrics */}
          <div className="card">
            <div className="card-header">
              <div className="card-icon" style={{ background: "rgba(251,191,36,0.15)" }}>
                <Zap className="icon-sm text-amber-300" />
              </div>
              <h2 className="card-title">System Metrics</h2>
              <span className="badge-live">LIVE</span>
            </div>

            {lastMetrics ? (
              <div className="metrics-stack">
                <div className={`metric-badge ${lastMetrics.cacheHit ? "metric-hit" : "metric-miss"}`}>
                  <div className="metric-badge-left">
                    <Zap className="icon-sm" />
                    <span className="metric-label">
                      {lastMetrics.cacheHit ? "REDIS CACHE HIT" : "vLLM INFERENCE"}
                    </span>
                  </div>
                  <span className="metric-tag">
                    {lastMetrics.cacheHit ? "< 10ms" : "Generated"}
                  </span>
                </div>

                <div className="metric-row">
                  <div className="metric-row-left">
                    <Clock className="icon-sm text-indigo-300" />
                    <span>Total Latency</span>
                  </div>
                  <span className="metric-value">{lastMetrics.latencyMs} ms</span>
                </div>

                <div className="metric-row">
                  <div className="metric-row-left">
                    <Layers className="icon-sm text-purple-300" />
                    <span>Chunks Retrieved</span>
                  </div>
                  <span className="metric-value">{lastMetrics.retrievedChunks}</span>
                </div>
              </div>
            ) : (
              <div className="empty-metric">
                <Activity className="icon-lg text-slate-600" />
                <p>Execute a query to see real-time cache & latency analytics</p>
              </div>
            )}
          </div>

          {/* Collection Stats */}
          <div className="card">
            <div className="card-header">
              <div className="card-icon" style={{ background: "rgba(129,140,248,0.15)" }}>
                <Server className="icon-sm text-indigo-300" />
              </div>
              <h2 className="card-title">Vector DB Stats</h2>
            </div>
            <div className="stats-grid">
              <div className="stat-item">
                <span className="stat-value">{collectionStats?.total_points ?? "—"}</span>
                <span className="stat-label">Indexed Chunks</span>
              </div>
              <div className="stat-item">
                <span className={`stat-value ${collectionStats?.status === "green" ? "text-emerald-300" : "text-amber-300"}`}>
                  {collectionStats?.status ?? "—"}
                </span>
                <span className="stat-label">Collection Status</span>
              </div>
            </div>
            <button onClick={fetchStats} className="refresh-btn">
              <RefreshCw className="icon-xs" />
              <span>Refresh</span>
            </button>
          </div>

          {/* Qdrant Context Inspector */}
          <div className="card flex-1">
            <div className="card-header">
              <div className="card-icon" style={{ background: "rgba(129,140,248,0.15)" }}>
                <Database className="icon-sm text-indigo-300" />
              </div>
              <h3 className="card-title">Retrieved Context</h3>
              <span className="badge-pill badge-indigo">{lastSources.length} chunks</span>
            </div>

            <div className="sources-list">
              {lastSources.length > 0 ? (
                lastSources.map((source, idx) => (
                  <div key={idx} className="source-item pop-in">
                    <div className="source-header">
                      <span className="source-label">Chunk #{idx + 1}</span>
                      <span className="source-score">
                        {source.score ? source.score.toFixed(4) : "N/A"}
                      </span>
                    </div>
                    <p className="source-file">
                      📄 {source.source_file || "unknown"}
                      {source.page_number ? ` · p.${source.page_number}` : ""}
                    </p>
                    <p className="source-text">{source.text || JSON.stringify(source)}</p>
                  </div>
                ))
              ) : (
                <div className="empty-sources">
                  <Layers className="icon-lg text-slate-600" />
                  <p>No context retrieved yet</p>
                </div>
              )}
            </div>
          </div>
        </aside>
      </div>

      {/* ── GUIDE MODAL ──────────────────────────────────────────────────────── */}
      {showGuideModal && (
        <div className="modal-backdrop" onClick={() => setShowGuideModal(false)}>
          <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-title-group">
                <div className="card-icon" style={{ background: "rgba(129,140,248,0.15)" }}>
                  <BookOpen className="icon-sm text-indigo-300" />
                </div>
                <div>
                  <h3 className="modal-title">How to Use & System Overview</h3>
                  <p className="modal-sub">Step-by-step guide to the RAG pipeline</p>
                </div>
              </div>
              <button onClick={() => setShowGuideModal(false)} className="modal-close">
                <X className="icon-sm" />
              </button>
            </div>

            <div className="guide-tabs">
              {[
                { num: 1, title: "1. Ingest" },
                { num: 2, title: "2. Ask AI" },
                { num: 3, title: "3. RBAC" },
                { num: 4, title: "4. Redis Cache" },
              ].map((step) => (
                <button
                  key={step.num}
                  onClick={() => setActiveGuideStep(step.num)}
                  className={`guide-tab ${activeGuideStep === step.num ? "guide-tab-active" : "guide-tab-inactive"}`}
                >
                  {step.title}
                </button>
              ))}
            </div>

            <div className="guide-content">
              {activeGuideStep === 1 && (
                <div className="guide-step">
                  <h4 className="guide-step-title">Step 1: Ingest Documents into Qdrant</h4>
                  <p>Paste any policy text into the <strong>Document Ingestion</strong> panel. Select department and clearance level, then click <strong>Ingest Document</strong>.</p>
                  <p>The system splits your text into <strong>512-character overlapping chunks</strong>, generates 384-dim BGE dense vectors + BM25 sparse vectors, and upserts both into Qdrant with RBAC metadata.</p>
                </div>
              )}
              {activeGuideStep === 2 && (
                <div className="guide-step">
                  <h4 className="guide-step-title">Step 2: Ask Natural Language Questions</h4>
                  <p>Type any question in the chat bar or click a <strong>Sample Question</strong>. Your query passes through input guardrails (PII redaction, prompt injection detection).</p>
                  <p>The backend then runs <strong>Hybrid Search (Dense BGE + BM25) with RRF fusion</strong> to retrieve the most relevant chunks, then feeds them to the LLM for grounded generation.</p>
                </div>
              )}
              {activeGuideStep === 3 && (
                <div className="guide-step">
                  <h4 className="guide-step-title">Step 3: Role-Based Access Control (RBAC)</h4>
                  <p>Select different roles in the <strong>Access Context</strong> panel. The <strong>Admin</strong> role bypasses all filters and sees all documents. <strong>Employee</strong> sees only their department + general docs within clearance level 2.</p>
                  <p>This filtering happens <strong>inside Qdrant at vector search time</strong> — unauthorized chunks are never even fetched, let alone shown to the LLM.</p>
                </div>
              )}
              {activeGuideStep === 4 && (
                <div className="guide-step">
                  <h4 className="guide-step-title">Step 4: Sub-10ms Redis Semantic Cache</h4>
                  <p>On first query you'll see <strong>vLLM INFERENCE</strong> (300–800ms). Ask the <em>same or a semantically similar question</em> again and the badge flips to a glowing <strong>REDIS CACHE HIT (&lt;10ms)</strong>!</p>
                  <p>The cache uses <strong>cosine similarity</strong> on stored query embeddings — so "What is the leave policy?" hits the same cache as "How many leave days do I get?"</p>
                </div>
              )}
            </div>

            <div className="modal-footer">
              <span className="modal-step-count">Step {activeGuideStep} of 4</span>
              <button
                onClick={() => activeGuideStep < 4 ? setActiveGuideStep(activeGuideStep + 1) : setShowGuideModal(false)}
                className="btn-primary btn-sm"
              >
                {activeGuideStep < 4 ? "Next →" : "Got It!"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
