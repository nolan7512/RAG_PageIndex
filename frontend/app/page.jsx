"use client";

import {
  AlertCircle,
  ArrowDownToLine,
  Bot,
  CheckCircle2,
  CircleDashed,
  Eye,
  Files,
  Folder,
  FolderTree,
  FileText,
  FolderUp,
  Layers3,
  Loader2,
  LogOut,
  MessageSquareText,
  RefreshCw,
  Search,
  Send,
  XCircle,
  Trash2,
  UploadCloud
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { apiFetch, downloadUrl } from "@/lib/api";

const statusConfig = {
  queued: { label: "Chờ xử lý", tone: "neutral" },
  processing: { label: "Đang xử lý", tone: "info" },
  ready: { label: "Sẵn sàng", tone: "success" },
  failed: { label: "Lỗi", tone: "danger" }
};

const supportedUploadExtensions = new Set(["pdf", "docx", "pptx", "xlsx", "txt", "png", "jpg", "jpeg"]);

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
  const [collectionTrees, setCollectionTrees] = useState([]);
  const [documentStatuses, setDocumentStatuses] = useState({});
  const [documentsLoading, setDocumentsLoading] = useState(true);
  const [collectionsLoading, setCollectionsLoading] = useState(true);
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
  const [uploading, setUploading] = useState(false);
  const [selectedScope, setSelectedScope] = useState({ type: "all", id: null, label: "Tất cả tài liệu" });
  const fileInputRef = useRef(null);
  const folderInputRef = useRef(null);

  const readyCount = useMemo(() => documents.filter((document) => document.status === "ready").length, [documents]);
  const processingCount = useMemo(
    () => documents.filter((document) => ["queued", "processing"].includes(document.status)).length,
    [documents]
  );
  const scopedDocuments = useMemo(
    () => documents.filter((document) => documentMatchesScope(document, selectedScope)),
    [documents, selectedScope]
  );

  const loadDocumentStatuses = useCallback(async (items) => {
    const visibleItems = items.slice(0, 12);
    const entries = await Promise.all(
      visibleItems.map(async (document) => {
        try {
          return [document.id, await apiFetch(`/documents/${document.id}/status`)];
        } catch {
          return [document.id, null];
        }
      })
    );
    setDocumentStatuses((current) => ({ ...current, ...Object.fromEntries(entries.filter(([, value]) => value)) }));
  }, []);

  const loadDocuments = useCallback(async () => {
    setDocumentsLoading(true);
    try {
      const items = await apiFetch("/documents");
      setDocuments(items);
      loadDocumentStatuses(items);
    } catch (err) {
      setNotice(err.message);
    } finally {
      setDocumentsLoading(false);
    }
  }, [loadDocumentStatuses]);

  const loadCollections = useCallback(async () => {
    setCollectionsLoading(true);
    try {
      const collections = await apiFetch("/collections");
      const trees = await Promise.all(
        collections.map(async (collection) => {
          try {
            return await apiFetch(`/collections/${collection.id}/tree`);
          } catch {
            return { ...collection, tree: { id: null, name: collection.name, path: "", depth: 0, children: [], documents: [] } };
          }
        })
      );
      setCollectionTrees(trees);
    } catch (err) {
      setNotice(err.message);
    } finally {
      setCollectionsLoading(false);
    }
  }, []);

  const reloadWorkspace = useCallback(async () => {
    await Promise.all([loadDocuments(), loadCollections()]);
  }, [loadDocuments, loadCollections]);

  useEffect(() => {
    reloadWorkspace();
  }, [reloadWorkspace]);

  useEffect(() => {
    if (!processingCount) return;
    const timer = setInterval(loadDocuments, 3500);
    return () => clearInterval(timer);
  }, [loadDocuments, processingCount]);

  async function uploadFiles(fileList, { sourceLabel = "file", preservePaths = false } = {}) {
    const files = Array.from(fileList || []);
    if (!files.length) return;
    setNotice("");
    setUploading(true);

    const acceptedFiles = files.filter((file) => {
      const extension = file.name.split(".").pop()?.toLowerCase();
      return extension && supportedUploadExtensions.has(extension);
    });

    if (!acceptedFiles.length) {
      setNotice("Không tìm thấy file hỗ trợ. Hệ thống nhận PDF, DOCX, PPTX, XLSX, TXT, PNG, JPG.");
      setUploading(false);
      return;
    }

    let uploadedCount = 0;
    const failedFiles = [];
    let collection = null;

    try {
      if (preservePaths) {
        const rootName = rootNameFromFiles(acceptedFiles);
        collection = await apiFetch("/collections", {
          method: "POST",
          body: JSON.stringify({ name: rootName, root_path: rootName })
        });
        setSelectedScope({ type: "collection", id: collection.id, label: collection.name, collectionId: collection.id });
      }
      for (const file of acceptedFiles) {
        const form = new FormData();
        form.append("file", file, file.name);
        form.append("relative_path", preservePaths ? relativePathForFile(file) : file.name);
        if (collection?.id) {
          form.append("collection_id", collection.id);
        }
        try {
          await apiFetch("/documents", { method: "POST", body: form });
          uploadedCount += 1;
          setNotice(`Đã gửi ${uploadedCount}/${acceptedFiles.length} ${sourceLabel} vào hàng đợi xử lý.`);
        } catch (err) {
          failedFiles.push(`${file.name}: ${err.message}`);
        }
      }
      await reloadWorkspace();
    } finally {
      setUploading(false);
    }

    if (failedFiles.length) {
      setNotice(`Đã gửi ${uploadedCount}/${acceptedFiles.length} file. Lỗi: ${failedFiles.slice(0, 3).join("; ")}`);
      return;
    }

    setNotice(
      sourceLabel === "file"
        ? `Đã gửi ${uploadedCount} file vào hàng đợi xử lý.`
        : `Đã gửi ${uploadedCount} file từ folder vào hàng đợi xử lý.`
    );
  }

  async function uploadFile(event) {
    await uploadFiles(event.target.files, { sourceLabel: "file" });
    event.target.value = "";
  }

  async function uploadFolder(event) {
    await uploadFiles(event.target.files, { sourceLabel: "file từ folder", preservePaths: true });
    event.target.value = "";
  }

  async function removeDocument(documentId) {
    setNotice("");
    try {
      await apiFetch(`/documents/${documentId}`, { method: "DELETE" });
      setReview((current) => (current?.document?.id === documentId ? null : current));
      await reloadWorkspace();
    } catch (err) {
      setNotice(err.message);
    }
  }

  async function refreshCollectionIndex(collectionId) {
    setNotice("");
    try {
      const result = await apiFetch(`/collections/${collectionId}/refresh-index`, { method: "POST" });
      await loadCollections();
      setNotice(
        `Đã refresh ${result.structure_index_count} index cho ${result.document_count} file. Trạng thái: ${result.status}.`
      );
    } catch (err) {
      setNotice(err.message);
    }
  }

  const [reviewPage, setReviewPage] = useState(1);

  async function openReview(documentId, pageNumber = 1) {
    setReviewLoading(true);
    setNotice("");
    setReviewPage(Math.max(1, Number(pageNumber) || 1));
    try {
      const [reviewPayload, statusPayload] = await Promise.all([
        apiFetch(`/documents/${documentId}/review`),
        apiFetch(`/documents/${documentId}/status`).catch(() => null)
      ]);
      setReview(reviewPayload);
      if (statusPayload) {
        setDocumentStatuses((current) => ({ ...current, [documentId]: statusPayload }));
      }
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
      setResults(
        await apiFetch("/search", {
          method: "POST",
          body: JSON.stringify({ query: trimmed, limit: 8, ...scopePayload(selectedScope) })
        })
      );
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
        body: JSON.stringify({ message: trimmed, conversation_id: conversationId, ...scopePayload(selectedScope) })
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
          <input
            ref={fileInputRef}
            type="file"
            className="visually-hidden"
            accept=".pdf,.docx,.pptx,.xlsx,.txt,.png,.jpg,.jpeg"
            multiple
            onChange={uploadFile}
          />
          <input
            ref={folderInputRef}
            type="file"
            className="visually-hidden"
            accept=".pdf,.docx,.pptx,.xlsx,.txt,.png,.jpg,.jpeg"
            webkitdirectory=""
            directory=""
            multiple
            onChange={uploadFolder}
          />
          <button className="primary-button" disabled={uploading} onClick={() => fileInputRef.current?.click()}>
            {uploading ? <Loader2 className="spin" size={16} aria-hidden="true" /> : <UploadCloud size={16} aria-hidden="true" />}
            Upload
          </button>
          <button className="ghost-button" disabled={uploading} onClick={() => folderInputRef.current?.click()}>
            <FolderUp size={16} aria-hidden="true" />
            Folder
          </button>
          <button className="icon-button" onClick={reloadWorkspace} title="Làm mới">
            <RefreshCw size={16} aria-hidden="true" />
          </button>
        </div>

        <div className="meter-row" aria-label="Tổng quan tài liệu">
          <span>{scopedDocuments.length}/{documents.length} file</span>
          <span>{readyCount} ready</span>
        </div>

        <ScopeTree
          trees={collectionTrees}
          loading={collectionsLoading}
          selectedScope={selectedScope}
          onSelectScope={setSelectedScope}
          onRefreshCollection={refreshCollectionIndex}
        />

        <DocumentList
          documents={scopedDocuments}
          loading={documentsLoading}
          onDelete={removeDocument}
          onDownload={(id) => window.open(downloadUrl(id), "_blank", "noopener,noreferrer")}
          onReview={openReview}
          selectedDocumentId={review?.document?.id}
          statuses={documentStatuses}
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
            <p>
              {processingCount ? `${processingCount} file đang xử lý` : "Index đã sẵn sàng"} · Scope: {selectedScope.label}
            </p>
          </div>
          {notice ? (
            <div className="notice" role="alert">
              <AlertCircle size={16} aria-hidden="true" />
              {notice}
            </div>
          ) : null}
        </header>

        <div className="work-grid">
          <ReviewPanel
            review={review}
            loading={reviewLoading}
            status={review?.document?.id ? documentStatuses[review.document.id] : null}
            activePage={reviewPage}
            onPageChange={setReviewPage}
            onClose={() => setReview(null)}
          />

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
                results.map((result) => <SearchResult key={result.chunk_id} result={result} onOpenPage={openReview} />)
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
                chatLog.map((item, index) => (
                  <ChatBubble key={`${item.role}-${index}`} item={item} onCitationClick={openReview} />
                ))
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

function ScopeTree({ trees, loading, selectedScope, onSelectScope, onRefreshCollection }) {
  if (loading) {
    return (
      <section className="scope-panel" aria-label="Folder tree">
        <div className="scope-heading">
          <FolderTree size={16} aria-hidden="true" />
          <strong>Scope</strong>
        </div>
        <div className="skeleton compact" />
      </section>
    );
  }

  return (
    <section className="scope-panel" aria-label="Folder tree">
      <div className="scope-heading">
        <FolderTree size={16} aria-hidden="true" />
        <strong>Scope</strong>
      </div>
      <button
        className={`tree-row root ${selectedScope.type === "all" ? "active" : ""}`}
        onClick={() => onSelectScope({ type: "all", id: null, label: "Tất cả tài liệu" })}
      >
        <Files size={15} aria-hidden="true" />
        <span>Tất cả tài liệu</span>
      </button>
      <div className="tree-list">
        {trees.length ? (
          trees.map((collection) => (
            <CollectionTreeNode
              collection={collection}
              key={collection.id}
              selectedScope={selectedScope}
              onSelectScope={onSelectScope}
              onRefreshCollection={onRefreshCollection}
            />
          ))
        ) : (
          <EmptyState text="Chưa có collection." />
        )}
      </div>
    </section>
  );
}

function CollectionTreeNode({ collection, selectedScope, onSelectScope, onRefreshCollection }) {
  const root = collection.tree || { children: [], documents: [] };
  return (
    <div className="tree-group">
      <div className={`tree-collection-line ${selectedScope.type === "collection" && selectedScope.id === collection.id ? "active" : ""}`}>
        <button
          className="tree-row collection"
          onClick={() =>
            onSelectScope({ type: "collection", id: collection.id, label: collection.name, collectionId: collection.id })
          }
        >
          <FolderTree size={15} aria-hidden="true" />
          <span title={collection.name}>{collection.name}</span>
        </button>
        <button
          className="tree-action"
          onClick={() => onRefreshCollection(collection.id)}
          title="Refresh folder/root index"
          aria-label={`Refresh index ${collection.name}`}
        >
          <RefreshCw size={13} aria-hidden="true" />
        </button>
      </div>
      <FolderTreeChildren
        node={root}
        collection={collection}
        level={1}
        selectedScope={selectedScope}
        onSelectScope={onSelectScope}
      />
    </div>
  );
}

function FolderTreeChildren({ node, collection, level, selectedScope, onSelectScope }) {
  const children = node?.children || [];
  const documents = node?.documents || [];
  return (
    <>
      {children.map((child) => (
        <div className="tree-branch" key={child.id || child.path}>
          <button
            className={`tree-row folder ${selectedScope.type === "folder" && selectedScope.id === child.id ? "active" : ""}`}
            style={{ "--level": level }}
            onClick={() =>
              onSelectScope({
                type: "folder",
                id: child.id,
                label: `${collection.name}/${child.path}`.replace(/\/$/, ""),
                collectionId: collection.id,
                folderPath: child.path
              })
            }
          >
            <Folder size={15} aria-hidden="true" />
            <span title={child.path}>{child.name}</span>
          </button>
          <FolderTreeChildren
            node={child}
            collection={collection}
            level={level + 1}
            selectedScope={selectedScope}
            onSelectScope={onSelectScope}
          />
        </div>
      ))}
      {documents.map((document) => (
        <button
          className={`tree-row document ${selectedScope.type === "document" && selectedScope.id === document.id ? "active" : ""}`}
          key={document.id}
          style={{ "--level": level }}
          onClick={() =>
            onSelectScope({
              type: "document",
              id: document.id,
              label: document.relative_path || document.filename,
              collectionId: collection.id,
              folderPath: document.folder_path || ""
            })
          }
        >
          <FileText size={14} aria-hidden="true" />
          <span title={document.relative_path || document.filename}>{document.relative_path || document.filename}</span>
        </button>
      ))}
    </>
  );
}

function DocumentList({ documents, loading, onDelete, onDownload, onReview, selectedDocumentId, statuses }) {
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
            <strong title={document.relative_path || document.filename}>{document.relative_path || document.filename}</strong>
            <span>
              {formatBytes(document.size_bytes)} · {document.page_count || 0} trang
            </span>
            {document.error_message ? <em>{document.error_message}</em> : null}
            <IngestionProgress steps={statuses?.[document.id]?.steps || []} compact />
            <IngestionSteps steps={statuses?.[document.id]?.steps || []} compact />
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

function ReviewPanel({ review, loading, status, activePage, onPageChange, onClose }) {
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
      <IngestionSteps steps={status?.steps || []} />
      <IngestionProgress steps={status?.steps || []} />

      <div className="review-grid">
        <div className="pdf-preview">
          {isPdf ? (
            <iframe
              key={`${review.document.id}-${activePage}`}
              title={`Preview ${review.document.filename}`}
              src={`${downloadUrl(review.document.id)}#page=${activePage}`}
            />
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
              firstBlocks.map((block, index) => (
                <ParsedBlock key={`${block.page_number}-${index}`} block={block} onOpenPage={onPageChange} />
              ))
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
              firstChunks.map((chunk) => <ReviewChunk key={chunk.id} chunk={chunk} onOpenPage={onPageChange} />)
            ) : (
              <EmptyState text="Chưa có chunk đã index." />
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

function ParsedBlock({ block, onOpenPage }) {
  const confidenceAvg = formatConfidence(block.metadata?.ocr_confidence_avg);
  const confidenceMin = formatConfidence(block.metadata?.ocr_confidence_min);
  const ocrLines = Array.isArray(block.metadata?.ocr_lines) ? block.metadata.ocr_lines.slice(0, 6) : [];
  return (
    <article className="review-row">
      <div className="result-meta">
        <button className="meta-button" onClick={() => onOpenPage(block.page_number)}>
          Trang {block.page_number}
        </button>
        <span>{block.block_type}</span>
        {block.metadata?.parser ? <span>{block.metadata.parser}</span> : null}
        {confidenceAvg ? <span>avg {confidenceAvg}</span> : null}
        {confidenceMin ? <span>min {confidenceMin}</span> : null}
        {block.metadata?.ocr_line_count ? <span>{block.metadata.ocr_line_count} dòng OCR</span> : null}
        {block.metadata?.paddleocr_available !== undefined ? (
          <span>paddle {block.metadata.paddleocr_available ? "yes" : "no"}</span>
        ) : null}
        {block.metadata?.vietocr_available !== undefined ? (
          <span>vietocr {block.metadata.vietocr_available ? "yes" : "no"}</span>
        ) : null}
        {block.metadata?.fallback_reason ? <span>{block.metadata.fallback_reason}</span> : null}
      </div>
      <pre>{block.content}</pre>
      {ocrLines.length ? <OcrLinePreview lines={ocrLines} /> : null}
    </article>
  );
}

function ReviewChunk({ chunk, onOpenPage }) {
  const confidenceAvg = formatConfidence(chunk.metadata?.ocr_confidence_avg);
  return (
    <article className="review-row">
      <div className="result-meta">
        <span>Chunk {chunk.chunk_index}</span>
        <button className="meta-button" onClick={() => onOpenPage(chunk.page_number)}>
          Trang {chunk.page_number}
        </button>
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

function SearchResult({ result, onOpenPage }) {
  return (
    <article className="result-row">
      <div className="result-meta">
        <span title={result.relative_path || result.filename}>{result.relative_path || result.filename}</span>
        <button className="meta-button" onClick={() => onOpenPage(result.document_id, result.page_number)}>
          Trang {result.page_number}
        </button>
        <span>{Math.round(result.score * 100)}%</span>
        {result.rerank_score ? <span>rerank {Math.round(result.rerank_score * 100)}%</span> : null}
      </div>
      <p>{result.excerpt}</p>
    </article>
  );
}

function ChatBubble({ item, onCitationClick }) {
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
            <div
              className="citation-row"
              key={citation.chunk_id}
            >
              <button
                className="citation-open"
                onClick={() => onCitationClick(citation.document_id, citation.page_number)}
              >
                <strong>{citation.relative_path || citation.filename}</strong>
                <span>Trang {citation.page_number}</span>
                <p>{citation.excerpt}</p>
              </button>
              <button
                className="citation-download"
                onClick={() => window.open(downloadUrl(citation.document_id), "_blank", "noopener,noreferrer")}
                title="Download file"
                aria-label={`Download ${citation.relative_path || citation.filename}`}
              >
                <ArrowDownToLine size={15} aria-hidden="true" />
              </button>
            </div>
          ))}
        </div>
      ) : null}
    </article>
  );
}

function IngestionSteps({ steps, compact = false }) {
  if (!steps?.length) return null;
  const visibleSteps = compact ? steps.filter((step) => step.status !== "pending") : steps;
  if (!visibleSteps.length) return null;
  return (
    <div className={`ingestion-steps ${compact ? "compact" : ""}`} aria-label="Ingestion progress">
      {visibleSteps.map((step) => (
        <div className={`ingestion-step ${step.status}`} key={step.name}>
          {step.status === "done" ? <CheckCircle2 size={13} /> : null}
          {step.status === "failed" ? <XCircle size={13} /> : null}
          {["processing", "pending", "skipped"].includes(step.status) ? <CircleDashed size={13} /> : null}
          <span>{stepLabel(step.name)}</span>
          {!compact && step.message ? <em>{step.message}</em> : null}
        </div>
      ))}
    </div>
  );
}

function IngestionProgress({ steps, compact = false }) {
  if (!steps?.length) return null;
  const summary = summarizeIngestionProgress(steps);
  if (!summary) return null;
  return (
    <div className={`ingestion-progress ${compact ? "compact" : ""}`} aria-label="Ingestion percent">
      <div className="progress-line">
        <strong>{summary.percent}%</strong>
        <span>{summary.label}</span>
        {!compact && summary.elapsed ? <em>{summary.elapsed}</em> : null}
      </div>
      <div className="progress-track" role="progressbar" aria-valuenow={summary.percent} aria-valuemin="0" aria-valuemax="100">
        <div className={`progress-fill ${summary.tone}`} style={{ width: `${summary.percent}%` }} />
      </div>
      {!compact ? (
        <div className="progress-detail">
          <span>{summary.completed}/{summary.total} bước hoàn tất</span>
          {summary.activeStep ? <span>Đang xử lý: {stepLabel(summary.activeStep.name)}</span> : null}
        </div>
      ) : null}
    </div>
  );
}

function summarizeIngestionProgress(steps) {
  const ordered = ["uploaded", "parsing", "ocr", "chunking", "embedding", "pageindex", "ready"];
  const visibleSteps = ordered.map((name) => steps.find((step) => step.name === name)).filter(Boolean);
  if (!visibleSteps.length) return null;

  const failedStep = visibleSteps.find((step) => step.status === "failed");
  const activeStep = visibleSteps.find((step) => step.status === "processing");
  const readyStep = visibleSteps.find((step) => step.name === "ready" && step.status === "done");
  const completed = visibleSteps.filter((step) => ["done", "skipped"].includes(step.status)).length;
  const total = visibleSteps.length;

  let percent = Math.round((completed / total) * 100);
  if (activeStep) {
    const activeIndex = Math.max(0, ordered.indexOf(activeStep.name));
    let activeProgress = 0.45;
    const processedChunks = Number(activeStep.metadata?.processed_chunks);
    const totalChunks = Number(activeStep.metadata?.total_chunks);
    if (activeStep.name === "embedding" && totalChunks > 0 && processedChunks >= 0) {
      activeProgress = Math.min(0.95, Math.max(0.05, processedChunks / totalChunks));
    }
    percent = Math.max(percent, Math.round(((activeIndex + activeProgress) / total) * 100));
  }
  if (readyStep) percent = 100;
  if (failedStep) percent = Math.max(5, percent);
  percent = Math.min(100, Math.max(0, percent));

  const startedAt = visibleSteps.find((step) => step.started_at)?.started_at || visibleSteps[0]?.started_at;
  const finishedAt = readyStep?.finished_at || failedStep?.finished_at;
  const elapsed = formatElapsed(startedAt, finishedAt);

  let label = readyStep ? "Hoàn tất" : `${percent}%`;
  let tone = readyStep ? "done" : "active";
  if (failedStep) {
    label = "Lỗi xử lý";
    tone = "failed";
  } else if (activeStep) {
    label = `${stepLabel(activeStep.name)} đang xử lý`;
    const processedChunks = Number(activeStep.metadata?.processed_chunks);
    const totalChunks = Number(activeStep.metadata?.total_chunks);
    if (activeStep.name === "embedding" && totalChunks > 0 && processedChunks >= 0) {
      label = `embedding ${processedChunks}/${totalChunks} chunk`;
    }
  }

  return { percent, label, tone, completed, total, activeStep, elapsed };
}

function stepLabel(name) {
  const labels = {
    uploaded: "uploaded",
    parsing: "parsing",
    ocr: "OCR",
    chunking: "chunking",
    embedding: "embedding",
    pageindex: "PageIndex",
    ready: "ready"
  };
  return labels[name] || name;
}

function scopePayload(scope) {
  if (!scope || scope.type === "all") {
    return { scope_type: "all", scope_id: null };
  }
  return { scope_type: scope.type, scope_id: scope.id };
}

function relativePathForFile(file) {
  return file?.webkitRelativePath || file?.name || "document";
}

function rootNameFromFiles(files) {
  const firstPath = relativePathForFile(files[0] || {});
  const root = firstPath.split(/[\\/]/).filter(Boolean)[0];
  return root || "Folder upload";
}

function documentMatchesScope(document, scope) {
  if (!scope || scope.type === "all") return true;
  if (scope.type === "collection") return document.collection_id === scope.id;
  if (scope.type === "document") return document.id === scope.id;
  if (scope.type === "folder") {
    if (document.collection_id !== scope.collectionId) return false;
    const folderPath = scope.folderPath || "";
    if (!folderPath) return true;
    return document.folder_path === folderPath || document.folder_path?.startsWith(`${folderPath}/`);
  }
  return true;
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

function formatElapsed(startedAt, finishedAt) {
  if (!startedAt) return "";
  const start = new Date(`${startedAt}Z`);
  const end = finishedAt ? new Date(`${finishedAt}Z`) : new Date();
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return "";
  const seconds = Math.max(0, Math.floor((end.getTime() - start.getTime()) / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  if (minutes < 60) return `${minutes}m ${rest}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}
