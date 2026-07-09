"use client";

import {
  AlertCircle,
  ArrowDownToLine,
  Bot,
  CheckCircle2,
  Eye,
  FileText,
  Layers3,
  Loader2,
  LogOut,
  MessageSquareText,
  RefreshCw,
  Search,
  Send,
  Trash2,
  UploadCloud
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { apiFetch, downloadUrl } from "@/lib/api";

const statusConfig = {
  queued: { label: "Chờ xử lý", tone: "neutral" },
  processing: { label: "Đang xử lý", tone: "info" },
  ready: { label: "Sẵn sàng", tone: "success" },
  failed: { label: "Lỗi", tone: "danger" }
};

export default function HomePage() {
  const [user, setUser] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [loginError, setLoginError] = useState("");

  useEffect(() => {
    apiFetch("/auth/me")
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setAuthLoading(false));
  }, []);

  if (authLoading) {
    return (
      <main className="center-shell">
        <Loader2 className="spin" aria-hidden="true" />
      </main>
    );
  }

  if (!user) {
    return <LoginScreen onLogin={setUser} error={loginError} setError={setLoginError} />;
  }

  return <Workbench user={user} onLogout={() => setUser(null)} />;
}

function LoginScreen({ onLogin, error, setError }) {
  const [email, setEmail] = useState("admin@example.com");
  const [password, setPassword] = useState("change-me-now");
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const user = await apiFetch("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password })
      });
      onLogin(user);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-shell">
      <section className="login-panel" aria-labelledby="login-title">
        <div className="brand-mark">
          <FileText size={22} aria-hidden="true" />
        </div>
        <h1 id="login-title">RAG PageIndex</h1>
        <form onSubmit={submit} className="login-form">
          <label>
            Email
            <input value={email} onChange={(event) => setEmail(event.target.value)} type="email" autoComplete="email" />
          </label>
          <label>
            Mật khẩu
            <input
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              type="password"
              autoComplete="current-password"
            />
          </label>
          {error ? <p className="inline-error">{error}</p> : null}
          <button className="primary-button" disabled={busy}>
            {busy ? <Loader2 className="spin" size={16} aria-hidden="true" /> : <CheckCircle2 size={16} aria-hidden="true" />}
            Đăng nhập
          </button>
        </form>
      </section>
    </main>
  );
}

function Workbench({ user, onLogout }) {
  const [documents, setDocuments] = useState([]);
  const [documentsLoading, setDocumentsLoading] = useState(true);
  const [notice, setNotice] = useState("");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [message, setMessage] = useState("");
  const [chatBusy, setChatBusy] = useState(false);
  const [conversationId, setConversationId] = useState(null);
  const [chatLog, setChatLog] = useState([]);
  const [review, setReview] = useState(null);
  const [reviewLoading, setReviewLoading] = useState(false);
  const fileInputRef = useRef(null);

  const readyCount = useMemo(() => documents.filter((document) => document.status === "ready").length, [documents]);
  const processingCount = useMemo(
    () => documents.filter((document) => ["queued", "processing"].includes(document.status)).length,
    [documents]
  );

  async function loadDocuments() {
    setDocumentsLoading(true);
    try {
      setDocuments(await apiFetch("/documents"));
    } catch (err) {
      setNotice(err.message);
    } finally {
      setDocumentsLoading(false);
    }
  }

  useEffect(() => {
    loadDocuments();
  }, []);

  useEffect(() => {
    if (!processingCount) return;
    const timer = setInterval(loadDocuments, 3500);
    return () => clearInterval(timer);
  }, [processingCount]);

  async function uploadFile(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    setNotice("");
    const form = new FormData();
    form.append("file", file);
    try {
      await apiFetch("/documents", { method: "POST", body: form });
      await loadDocuments();
    } catch (err) {
      setNotice(err.message);
    } finally {
      event.target.value = "";
    }
  }

  async function removeDocument(documentId) {
    setNotice("");
    try {
      await apiFetch(`/documents/${documentId}`, { method: "DELETE" });
      setReview((current) => (current?.document?.id === documentId ? null : current));
      await loadDocuments();
    } catch (err) {
      setNotice(err.message);
    }
  }

  async function openReview(documentId) {
    setReviewLoading(true);
    setNotice("");
    try {
      setReview(await apiFetch(`/documents/${documentId}/review`));
    } catch (err) {
      setNotice(err.message);
    } finally {
      setReviewLoading(false);
    }
  }

  async function logout() {
    await apiFetch("/auth/logout", { method: "POST" }).catch(() => null);
    onLogout();
  }

  async function submitSearch(event) {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;
    setSearching(true);
    setNotice("");
    try {
      setResults(await apiFetch("/search", { method: "POST", body: JSON.stringify({ query: trimmed, limit: 8 }) }));
    } catch (err) {
      setNotice(err.message);
    } finally {
      setSearching(false);
    }
  }

  async function submitChat(event) {
    event.preventDefault();
    const trimmed = message.trim();
    if (!trimmed) return;
    setChatBusy(true);
    setNotice("");
    setMessage("");
    setChatLog((items) => [...items, { role: "user", content: trimmed, citations: [] }]);
    try {
      const response = await apiFetch("/chat", {
        method: "POST",
        body: JSON.stringify({ message: trimmed, conversation_id: conversationId })
      });
      setConversationId(response.conversation_id);
      setChatLog((items) => [...items, { role: "assistant", content: response.answer, citations: response.citations }]);
    } catch (err) {
      setNotice(err.message);
      setChatLog((items) => [...items, { role: "assistant", content: `Lỗi: ${err.message}`, citations: [] }]);
    } finally {
      setChatBusy(false);
    }
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="app-title">
          <div className="brand-mark small">
            <FileText size={18} aria-hidden="true" />
          </div>
          <div>
            <strong>RAG PageIndex</strong>
            <span>{user.email}</span>
          </div>
        </div>

        <div className="sidebar-actions">
          <input ref={fileInputRef} type="file" className="visually-hidden" onChange={uploadFile} />
          <button className="primary-button" onClick={() => fileInputRef.current?.click()}>
            <UploadCloud size={16} aria-hidden="true" />
            Upload
          </button>
          <button className="icon-button" onClick={loadDocuments} title="Làm mới">
            <RefreshCw size={16} aria-hidden="true" />
          </button>
        </div>

        <div className="meter-row" aria-label="Tổng quan tài liệu">
          <span>{documents.length} file</span>
          <span>{readyCount} ready</span>
        </div>

        <DocumentList
          documents={documents}
          loading={documentsLoading}
          onDelete={removeDocument}
          onDownload={(id) => window.open(downloadUrl(id), "_blank", "noopener,noreferrer")}
          onReview={openReview}
          selectedDocumentId={review?.document?.id}
        />

        <button className="ghost-button logout" onClick={logout}>
          <LogOut size={16} aria-hidden="true" />
          Đăng xuất
        </button>
      </aside>

      <section className="workspace">
        <header className="workspace-header">
          <div>
            <h1>Document RAG</h1>
            <p>{processingCount ? `${processingCount} file đang xử lý` : "Index đã sẵn sàng"}</p>
          </div>
          {notice ? (
            <div className="notice" role="alert">
              <AlertCircle size={16} aria-hidden="true" />
              {notice}
            </div>
          ) : null}
        </header>

        <div className="work-grid">
          <ReviewPanel review={review} loading={reviewLoading} onClose={() => setReview(null)} />

          <section className="tool-panel search-panel" aria-labelledby="search-title">
            <div className="panel-heading">
              <Search size={17} aria-hidden="true" />
              <h2 id="search-title">Search</h2>
            </div>
            <form className="query-row" onSubmit={submitSearch}>
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Tìm điều khoản, số liệu, nội dung..."
              />
              <button className="primary-button compact" disabled={searching}>
                {searching ? <Loader2 className="spin" size={16} aria-hidden="true" /> : <Search size={16} aria-hidden="true" />}
                Tìm
              </button>
            </form>
            <div className="result-list">
              {results.length ? (
                results.map((result) => <SearchResult key={result.chunk_id} result={result} />)
              ) : (
                <EmptyState text="Chưa có kết quả." />
              )}
            </div>
          </section>

          <section className="tool-panel chat-panel" aria-labelledby="chat-title">
            <div className="panel-heading">
              <MessageSquareText size={17} aria-hidden="true" />
              <h2 id="chat-title">Chat</h2>
            </div>
            <div className="chat-log">
              {chatLog.length ? (
                chatLog.map((item, index) => <ChatBubble key={`${item.role}-${index}`} item={item} />)
              ) : (
                <EmptyState text="Đặt câu hỏi trên tài liệu đã index." />
              )}
            </div>
            <form className="chat-input" onSubmit={submitChat}>
              <input
                value={message}
                onChange={(event) => setMessage(event.target.value)}
                placeholder="Hỏi theo nội dung tài liệu..."
              />
              <button className="primary-button compact" disabled={chatBusy}>
                {chatBusy ? <Loader2 className="spin" size={16} aria-hidden="true" /> : <Send size={16} aria-hidden="true" />}
                Gửi
              </button>
            </form>
          </section>
        </div>
      </section>
    </main>
  );
}

function DocumentList({ documents, loading, onDelete, onDownload, onReview, selectedDocumentId }) {
  if (loading) {
    return (
      <div className="document-list">
        <div className="skeleton" />
        <div className="skeleton" />
        <div className="skeleton" />
      </div>
    );
  }

  if (!documents.length) {
    return <EmptyState text="Chưa có file." />;
  }

  return (
    <div className="document-list">
      {documents.map((document) => (
        <article className={`document-row ${selectedDocumentId === document.id ? "selected" : ""}`} key={document.id}>
          <div className="file-icon">
            <FileText size={17} aria-hidden="true" />
          </div>
          <div className="document-main">
            <strong title={document.filename}>{document.filename}</strong>
            <span>
              {formatBytes(document.size_bytes)} · {document.page_count || 0} trang
            </span>
            {document.error_message ? <em>{document.error_message}</em> : null}
          </div>
          <StatusBadge status={document.status} />
          <div className="row-actions">
            <button className="icon-button" onClick={() => onReview(document.id)} title="Review OCR/RAG">
              <Eye size={15} aria-hidden="true" />
            </button>
            <button className="icon-button" onClick={() => onDownload(document.id)} title="Download">
              <ArrowDownToLine size={15} aria-hidden="true" />
            </button>
            <button className="icon-button danger" onClick={() => onDelete(document.id)} title="Xóa">
              <Trash2 size={15} aria-hidden="true" />
            </button>
          </div>
        </article>
      ))}
    </div>
  );
}

function ReviewPanel({ review, loading, onClose }) {
  if (loading) {
    return (
      <section className="tool-panel review-panel" aria-labelledby="review-title">
        <div className="panel-heading">
          <Loader2 className="spin" size={17} aria-hidden="true" />
          <h2 id="review-title">Review OCR / RAG</h2>
        </div>
        <div className="review-empty">
          <div className="skeleton" />
        </div>
      </section>
    );
  }

  if (!review) {
    return (
      <section className="tool-panel review-panel compact-review" aria-labelledby="review-title">
        <div className="panel-heading">
          <Eye size={17} aria-hidden="true" />
          <h2 id="review-title">Review OCR / RAG</h2>
        </div>
        <div className="review-empty">
          <EmptyState text="Chọn biểu tượng mắt ở một file để xem PDF gốc và text mà parser/OCR đã trích xuất." />
        </div>
      </section>
    );
  }

  const isPdf = review.document.mime_type?.includes("pdf") || review.document.filename.toLowerCase().endsWith(".pdf");
  const firstBlocks = review.parsed_blocks.slice(0, 80);
  const firstChunks = review.chunks.slice(0, 80);

  return (
    <section className="tool-panel review-panel" aria-labelledby="review-title">
      <div className="panel-heading review-heading">
        <div>
          <div className="heading-line">
            <Eye size={17} aria-hidden="true" />
            <h2 id="review-title">Review OCR / RAG</h2>
          </div>
          <p>{review.document.filename}</p>
        </div>
        <button className="ghost-button" onClick={onClose}>
          Đóng
        </button>
      </div>

      <div className="review-summary" aria-label="Parser summary">
        <span>{review.document.page_count || 0} trang</span>
        <span>{review.parsed_block_count} block parse</span>
        <span>{review.chunk_count} chunk</span>
        <span>{review.total_tokens} token</span>
        <span>{review.parser_names.length ? review.parser_names.join(", ") : "parser chưa rõ"}</span>
      </div>

      <div className="review-grid">
        <div className="pdf-preview">
          {isPdf ? (
            <iframe title={`Preview ${review.document.filename}`} src={downloadUrl(review.document.id)} />
          ) : (
            <EmptyState text="Preview gốc hiện ưu tiên PDF. Dùng nút download để xem file Office/ảnh." />
          )}
        </div>

        <div className="extraction-review">
          <div className="review-section-title">
            <Layers3 size={16} aria-hidden="true" />
            <strong>Parsed blocks</strong>
          </div>
          <div className="review-list">
            {firstBlocks.length ? (
              firstBlocks.map((block, index) => <ParsedBlock key={`${block.page_number}-${index}`} block={block} />)
            ) : (
              <EmptyState text="Chưa có parsed artifact. File có thể đang xử lý hoặc parser lỗi." />
            )}
          </div>

          <div className="review-section-title">
            <FileText size={16} aria-hidden="true" />
            <strong>Indexed chunks</strong>
          </div>
          <div className="review-list chunks">
            {firstChunks.length ? (
              firstChunks.map((chunk) => <ReviewChunk key={chunk.id} chunk={chunk} />)
            ) : (
              <EmptyState text="Chưa có chunk đã index." />
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

function ParsedBlock({ block }) {
  const confidenceAvg = formatConfidence(block.metadata?.ocr_confidence_avg);
  const confidenceMin = formatConfidence(block.metadata?.ocr_confidence_min);
  const ocrLines = Array.isArray(block.metadata?.ocr_lines) ? block.metadata.ocr_lines.slice(0, 6) : [];
  return (
    <article className="review-row">
      <div className="result-meta">
        <span>Trang {block.page_number}</span>
        <span>{block.block_type}</span>
        {block.metadata?.parser ? <span>{block.metadata.parser}</span> : null}
        {confidenceAvg ? <span>avg {confidenceAvg}</span> : null}
        {confidenceMin ? <span>min {confidenceMin}</span> : null}
        {block.metadata?.ocr_line_count ? <span>{block.metadata.ocr_line_count} dòng OCR</span> : null}
      </div>
      <pre>{block.content}</pre>
      {ocrLines.length ? <OcrLinePreview lines={ocrLines} /> : null}
    </article>
  );
}

function ReviewChunk({ chunk }) {
  const confidenceAvg = formatConfidence(chunk.metadata?.ocr_confidence_avg);
  return (
    <article className="review-row">
      <div className="result-meta">
        <span>Chunk {chunk.chunk_index}</span>
        <span>Trang {chunk.page_number}</span>
        <span>{chunk.content_type}</span>
        <span>{chunk.token_count} token</span>
        {chunk.metadata?.parser ? <span>{chunk.metadata.parser}</span> : null}
        {confidenceAvg ? <span>avg {confidenceAvg}</span> : null}
      </div>
      <pre>{chunk.content}</pre>
    </article>
  );
}

function OcrLinePreview({ lines }) {
  return (
    <div className="ocr-lines" aria-label="OCR confidence preview">
      {lines.map((line, index) => (
        <div key={`${line.text}-${index}`} className="ocr-line">
          <span>{formatConfidence(line.confidence) || "--"}</span>
          <p>{line.text}</p>
        </div>
      ))}
    </div>
  );
}

function formatConfidence(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "";
  }
  return `${Math.round(Number(value) * 100)}%`;
}

function StatusBadge({ status }) {
  const config = statusConfig[status] || statusConfig.queued;
  return <span className={`status-badge ${config.tone}`}>{config.label}</span>;
}

function SearchResult({ result }) {
  return (
    <article className="result-row">
      <div className="result-meta">
        <span>{result.filename}</span>
        <span>Trang {result.page_number}</span>
        <span>{Math.round(result.score * 100)}%</span>
      </div>
      <p>{result.excerpt}</p>
    </article>
  );
}

function ChatBubble({ item }) {
  const isAssistant = item.role === "assistant";
  return (
    <article className={`chat-bubble ${isAssistant ? "assistant" : "user"}`}>
      <div className="bubble-role">
        {isAssistant ? <Bot size={15} aria-hidden="true" /> : <MessageSquareText size={15} aria-hidden="true" />}
        <span>{isAssistant ? "Assistant" : "Bạn"}</span>
      </div>
      <p>{item.content}</p>
      {item.citations?.length ? (
        <div className="citation-list">
          {item.citations.map((citation) => (
            <div className="citation-row" key={citation.chunk_id}>
              <strong>{citation.filename}</strong>
              <span>Trang {citation.page_number}</span>
              <p>{citation.excerpt}</p>
            </div>
          ))}
        </div>
      ) : null}
    </article>
  );
}

function EmptyState({ text }) {
  return <div className="empty-state">{text}</div>;
}

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`;
}
