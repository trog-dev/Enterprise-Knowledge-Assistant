import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError, getAll, jsonRequest } from "./api";
import type { ChatResponse, Conversation, Profile, TokenResponse, Turn } from "./api";
import Icon from "./Icon";
import DocumentManager from "./DocumentManager";
import UserManager from "./UserManager";
import "./App.css";

type View = "chat" | "documents" | "users";

export default function App() {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<Profile | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [view, setView] = useState<View>("chat");
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [historySearch, setHistorySearch] = useState("");
  const [copiedTurn, setCopiedTurn] = useState<number | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState("");
  const [error, setError] = useState("");
  const requestLock = useRef(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const sidebarRef = useRef<HTMLElement>(null);
  const drawerCloseRef = useRef<HTMLButtonElement>(null);

  const clearSession = useCallback((message = "") => {
    setToken(null); setUser(null); setView("chat"); setConversations([]);
    setMobileNavOpen(false); setHistorySearch(""); setCopiedTurn(null);
    setConversationId(null); setTurns([]); setQuestion(""); setPassword("");
    setBusy(false); setPending(""); setError(message);
  }, []);

  const sessionExpired = useCallback(() => {
    clearSession("Phiên đăng nhập đã hết hạn hoặc tài khoản bị khóa. Vui lòng đăng nhập lại.");
  }, [clearSession]);

  useEffect(() => {
    if (typeof bottomRef.current?.scrollIntoView === "function") {
      bottomRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [turns, view]);

  useEffect(() => {
    const isMobile = () => window.matchMedia?.("(max-width: 800px)").matches ?? false;
    if (!mobileNavOpen || !isMobile()) return;
    const previousFocus = document.activeElement;
    drawerCloseRef.current?.focus();
    function handleKey(event: KeyboardEvent) {
      if (!isMobile()) return;
      if (event.key === "Escape") { event.preventDefault(); setMobileNavOpen(false); }
      if (event.key !== "Tab") return;
      const controls = Array.from(sidebarRef.current?.querySelectorAll<HTMLElement>(
        "button:not(:disabled), input:not(:disabled), a[href], [tabindex='0']"
      ) ?? []).filter((item) => item.getClientRects().length > 0);
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("keydown", handleKey);
      if (isMobile() && previousFocus instanceof HTMLElement) previousFocus.focus();
    };
  }, [mobileNavOpen]);

  function handleError(value: unknown) {
    if (value instanceof ApiError && value.status === 401) {
      if (token) sessionExpired();
      else setError("Email hoặc mật khẩu không đúng, hoặc tài khoản đã bị khóa.");
      return;
    }
    setError(value instanceof Error ? value.message : "Đã xảy ra lỗi.");
  }

  async function run(label: string, action: () => Promise<void>) {
    if (requestLock.current || busy) return;
    requestLock.current = true;
    setBusy(true); setPending(label); setError("");
    try { await action(); }
    catch (value) { handleError(value); }
    finally { requestLock.current = false; setBusy(false); setPending(""); }
  }

  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await run("Đang đăng nhập...", async () => {
      const result = await api<TokenResponse>("/auth/login", null, {
        method: "POST", body: new URLSearchParams({ username: email.trim(), password }),
      });
      const profile = await api<Profile>("/auth/me", result.access_token);
      if (!profile.is_active || !["admin", "employee"].includes(profile.role)) {
        throw new Error("Tài khoản không có quyền sử dụng ứng dụng.");
      }
      const items = await getAll<Conversation>("/conversations", result.access_token);
      setToken(result.access_token); setUser(profile); setConversations(items);
      setConversationId(null); setTurns([]); setView("chat"); setPassword("");
    });
  }

  function newConversation() {
    if (busy) return;
    setView("chat"); setConversationId(null); setTurns([]); setQuestion(""); setError("");
    setMobileNavOpen(false); setCopiedTurn(null);
  }

  async function openConversation(id: number) {
    if (!token) return;
    await run("Đang tải hội thoại...", async () => {
      const items = await getAll<Turn>(`/conversations/${id}/turns`, token);
      setConversationId(id); setTurns(items); setQuestion(""); setView("chat");
      setMobileNavOpen(false); setCopiedTurn(null);
    });
  }

  async function refreshHistory() {
    if (!token) return;
    await run("Đang tải lịch sử...", async () => {
      setConversations(await getAll<Conversation>("/conversations", token));
    });
  }

  async function sendQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = question.trim();
    if (!token || !text) return;
    await run("Đang tìm nguồn và tạo câu trả lời...", async () => {
      const result = await api<ChatResponse>("/chat", token, jsonRequest("POST", {
        question: text, top_k: 3, conversation_id: conversationId,
      }));
      setConversationId(result.conversation_id);
      setTurns((previous) => [...previous, {
        id: result.turn_id, conversation_id: result.conversation_id,
        question: result.question, answer: result.answer,
        sufficient: result.sufficient, sources: result.sources,
      }]);
      setConversations((previous) => previous.some((item) => item.id === result.conversation_id)
        ? previous : [{ id: result.conversation_id, title: text.slice(0, 120), created_at: new Date().toISOString() }, ...previous]);
      setQuestion("");
    });
  }

  function navigate(next: View) { if (!busy) { setView(next); setError(""); setMobileNavOpen(false); } }

  async function copyAnswer(id: number, text: string) {
    try {
      if (!navigator.clipboard) throw new Error("Trình duyệt chưa hỗ trợ sao chép. Bạn có thể chọn văn bản và nhấn Ctrl+C.");
      await navigator.clipboard.writeText(text);
      setCopiedTurn(id);
    } catch (value) {
      setError(value instanceof Error ? value.message : "Không sao chép được câu trả lời.");
    }
  }

  if (!token || !user) return <main className="login-page">
    <section className="login-story" aria-label="Giới thiệu ứng dụng">
      <div className="story-brand"><span className="brand-mark"><Icon name="grid" size={23} /></span><strong>Knowledge<span>Workspace</span></strong></div>
      <div className="story-content"><span className="story-kicker"><span />KHÔNG GIAN TRI THỨC NỘI BỘ</span>
        <h1>Tri thức kết nối.<br /><em>Quyết định rõ ràng.</em></h1>
        <p>Đưa tài liệu doanh nghiệp vào một không gian chung. Tìm câu trả lời, kiểm tra nguồn và chia sẻ đúng người.</p>
        <div className="story-preview" aria-hidden="true"><div className="preview-top"><span className="preview-icon"><Icon name="sparkles" /></span><div><strong>Câu trả lời bắt đầu từ tài liệu</strong><small>Hỏi đáp · Nguồn tham khảo · Phân quyền</small></div><Icon name="shield" /></div>
          <div className="preview-line long" /><div className="preview-line" /><div className="preview-line medium" />
          <div className="preview-sources"><span><Icon name="documents" size={14} />Tài liệu nội bộ</span><span><Icon name="check" size={14} />Có nguồn đối chiếu</span></div>
        </div>
        <div className="story-features"><span><Icon name="search" size={17} />Tìm kiếm theo nghĩa</span><span><Icon name="lock" size={17} />Quyền theo phòng ban</span></div>
      </div><footer className="story-footer">Enterprise Knowledge Assistant<span>Tri thức của đội ngũ, trong tầm tay.</span></footer>
    </section>
    <section className="login-form-area"><form className="login-card" onSubmit={login}>
      <span className="login-symbol"><Icon name="shield" size={27} /></span><p className="eyebrow">CHÀO MỪNG TRỞ LẠI</p>
      <h2>Đăng nhập không gian<br />làm việc của bạn</h2><p className="login-description">Tiếp tục khám phá tri thức và hội thoại của bạn.</p>
      <label htmlFor="login-email">Email</label><div className="input-shell"><Icon name="users" size={18} /><input id="login-email" type="email" value={email} required disabled={busy} autoComplete="username" placeholder="ten@congty.com" onChange={(event) => setEmail(event.target.value)} /></div>
      <label htmlFor="login-password">Mật khẩu</label><div className="input-shell"><Icon name="lock" size={18} /><input id="login-password" type="password" value={password} required disabled={busy} autoComplete="current-password" placeholder="Nhập mật khẩu của bạn" onChange={(event) => setPassword(event.target.value)} /></div>
      {error && <p className="error" role="alert">{error}</p>}
      <button className="primary login-submit" type="submit" disabled={busy}>{busy ? "Đang đăng nhập..." : "Đăng nhập"}<Icon name="arrow" size={18} /></button>
      <p className="login-footnote"><Icon name="lock" size={14} />Sử dụng tài khoản được quản trị viên cấp.</p>
    </form><small className="login-copyright">Enterprise Knowledge Assistant · Không gian làm việc nội bộ</small></section>
  </main>;

  const pageName = view === "documents" ? "Kho tài liệu" : view === "users" ? "Nhân viên & phòng ban" : "Trợ lý tri thức";
  const initials = user.full_name.split(/\s+/).filter(Boolean).map((part) => part[0]).slice(0, 2).join("").toUpperCase();
  const visibleHistory = conversations.filter((item) => item.title.toLocaleLowerCase("vi").includes(historySearch.toLocaleLowerCase("vi")));

  return <div className="workspace">
    {mobileNavOpen && <button className="sidebar-backdrop" aria-label="Đóng menu" onClick={() => setMobileNavOpen(false)} />}
    <aside ref={sidebarRef} className={`sidebar ${mobileNavOpen ? "drawer-open" : ""}`}>
      <div className="sidebar-brand"><span className="brand-mark"><Icon name="grid" size={22} /></span><div><strong>Knowledge</strong><small>ENTERPRISE WORKSPACE</small></div><button ref={drawerCloseRef} className="drawer-close icon-button" aria-label="Đóng menu" onClick={() => setMobileNavOpen(false)}><Icon name="close" /></button></div>
      <button className="new-chat-button" aria-label="+ Hội thoại mới" disabled={busy} onClick={newConversation}><Icon name="plus" size={19} />Hội thoại mới</button>
      <p className="nav-section-label">KHÔNG GIAN LÀM VIỆC</p>
      <nav className="main-nav" aria-label="Chức năng">
        <button className={view === "chat" ? "nav-active" : ""} disabled={busy} onClick={() => navigate("chat")}><Icon name="chat" />Hỏi đáp tài liệu{view === "chat" && <span className="nav-active-dot" />}</button>
        <button className={view === "documents" ? "nav-active" : ""} disabled={busy} onClick={() => navigate("documents")}><Icon name="documents" />{user.role === "admin" ? "Quản lý tài liệu" : "Tài liệu được phép đọc"}{view === "documents" && <span className="nav-active-dot" />}</button>
        {user.role === "admin" && <button className={view === "users" ? "nav-active" : ""} disabled={busy} onClick={() => navigate("users")}><Icon name="users" />Nhân viên & phòng ban{view === "users" && <span className="nav-active-dot" />}</button>}
      </nav>
      <div className="history-heading"><span>HỘI THOẠI GẦN ĐÂY</span><button className="icon-button" aria-label="Làm mới lịch sử hội thoại" disabled={busy} onClick={refreshHistory}><Icon name="refresh" size={15} /></button></div>
      {conversations.length > 0 && <div className="history-search"><Icon name="search" size={14} /><input aria-label="Tìm hội thoại" placeholder="Tìm hội thoại..." value={historySearch} onChange={(event) => setHistorySearch(event.target.value)} /></div>}
      <nav className="conversation-list" aria-label="Hội thoại">
        {conversations.length === 0 && <div className="history-empty"><Icon name="chat" size={22} /><p>Các cuộc trò chuyện của bạn<br />sẽ xuất hiện tại đây.</p></div>}
        {conversations.length > 0 && visibleHistory.length === 0 && <p className="muted">Không tìm thấy hội thoại.</p>}
        {visibleHistory.map((item) => <button key={item.id} title={item.title} disabled={busy}
          className={`conversation-button ${view === "chat" && item.id === conversationId ? "selected" : ""}`}
          onClick={() => openConversation(item.id)}><Icon name="chat" size={15} /><span>{item.title}</span></button>)}
      </nav>
      <div className="sidebar-tip"><span><Icon name="shield" size={16} />Đúng nguồn. Đúng quyền.</span><p>Chỉ tra cứu tài liệu tài khoản của bạn được phép truy cập.</p></div>
      <div className="profile-box"><span className="profile-avatar">{initials}</span><div><strong>{user.full_name}</strong><small>{user.role === "admin" ? "Quản trị viên" : "Nhân viên"}</small></div><button className="icon-button logout-button" title="Đăng xuất" aria-label="Đăng xuất" disabled={busy} onClick={() => clearSession()}><Icon name="logout" size={18} /></button></div>
    </aside>
    <main className="main-panel">
      <header className="workspace-bar"><div className="breadcrumb"><button className="mobile-menu icon-button" aria-label="Mở menu" onClick={() => setMobileNavOpen(true)}><Icon name="menu" /></button><span>Không gian làm việc</span><Icon name="chevron" size={14} /><strong>{pageName}</strong></div><div className="workspace-account"><span className="account-role"><span className="status-dot" />{user.role === "admin" ? "Quản trị viên" : "Nhân viên"}</span><span className="topbar-avatar" title={user.email}>{initials}</span></div></header>
      <div className="workspace-content">
      {view === "documents" ? <DocumentManager token={token} user={user} onBusyChange={setBusy} onSessionExpired={sessionExpired} />
        : view === "users" && user.role === "admin" ? <UserManager token={token} user={user} onBusyChange={setBusy} onSessionExpired={sessionExpired} />
        : <>
          <header className="chat-header"><div><h1>Trợ lý tri thức doanh nghiệp <span className="ai-label" aria-hidden="true"><Icon name="sparkles" size={12} />AI</span></h1><p>Tìm câu trả lời từ tài liệu của đội ngũ, kèm nguồn để đối chiếu.</p></div><span className="conversation-tag"><Icon name="chat" size={14} />{conversationId ? `Hội thoại #${conversationId}` : "Hội thoại mới"}</span></header>
          <section className={`messages ${turns.length === 0 ? "messages-empty" : ""}`} aria-label="Nội dung hội thoại" aria-busy={busy}>
            {turns.length === 0 && <div className="empty-state"><div className="hero-orbit"><span className="orbit-dot one" /><span className="orbit-dot two" /><span className="empty-icon"><Icon name="sparkles" size={34} /></span></div><span className="welcome-label">TRỢ LÝ CỦA ĐỘI NGŨ BẠN</span><h2>Tri thức doanh nghiệp,<br /><span>chỉ một câu hỏi.</span></h2><p>Hỏi điều bạn cần. Mình sẽ tìm thông tin trong tài liệu<br className="desktop-break" />được cấp quyền và dẫn nguồn rõ ràng.</p>
              <div className="suggestion-grid">
                <button disabled={busy} onClick={() => setQuestion("Cần báo nghỉ trước mấy ngày?")}><span className="suggestion-icon tone-teal"><Icon name="clock" size={18} /></span><strong>Tra cứu quy định</strong><small>Tôi cần báo nghỉ trước bao lâu?</small><Icon name="arrow" size={16} /></button>
                <button disabled={busy} onClick={() => setQuestion("Ai phê duyệt yêu cầu nghỉ phép?")}><span className="suggestion-icon tone-blue"><Icon name="users" size={18} /></span><strong>Tìm đúng người</strong><small>Ai phụ trách phê duyệt?</small><Icon name="arrow" size={16} /></button>
                <button disabled={busy} onClick={() => setQuestion("Quy trình gửi yêu cầu nghỉ phép gồm những bước nào?")}><span className="suggestion-icon tone-violet"><Icon name="documents" size={18} /></span><strong>Hiểu quy trình</strong><small>Các bước thực hiện thế nào?</small><Icon name="arrow" size={16} /></button>
              </div><div className="empty-access-note"><Icon name="shield" size={14} />Nguồn trả lời được giới hạn theo quyền của bạn.</div>
            </div>}
            {turns.map((turn) => <article className="turn" key={turn.id}>
              <div className="question"><div className="message-author"><span className="message-avatar user-avatar">{initials}</span><span>Bạn</span></div><p>{turn.question}</p></div>
              <div className="answer"><div className="message-author"><span className="message-avatar assistant-avatar"><Icon name="sparkles" size={17} /></span><span>Trợ lý tri thức</span>{turn.sources.length > 0 && <small className="answer-source-count">{turn.sources.length} nguồn tham khảo</small>}</div><p>{turn.answer}</p>
                {!turn.sufficient && <div className="insufficient-note"><Icon name="shield" size={15} /><small>Chưa đủ thông tin hoặc nội dung bị giới hạn quyền truy cập.</small></div>}
                {turn.sources.length > 0 && <div className="sources"><div className="source-heading"><Icon name="documents" size={14} /><strong>Nguồn tham khảo</strong><span>{turn.sources.length}</span></div>{turn.sources.map((source) => <details key={source.source_id}><summary><span className="source-file-icon"><Icon name="documents" size={17} /></span><span className="source-title">[{source.source_id}] {source.document_name} · {source.page_number != null ? `Trang ${source.page_number}` : source.source_location ?? `Đoạn ${source.chunk_index + 1}`}</span><Icon name="chevron" size={15} /></summary><p>{source.content}</p></details>)}</div>}
                <div className="answer-actions"><button className="text-button" onClick={() => copyAnswer(turn.id, turn.answer)}><Icon name={copiedTurn === turn.id ? "check" : "copy"} size={14} />{copiedTurn === turn.id ? "Đã sao chép" : "Sao chép câu trả lời"}</button></div>
              </div>
            </article>)}
            <div ref={bottomRef} />
          </section>
          <footer className="composer">
            {error && <p className="error" role="alert">{error}</p>}
            {pending && <p className="thinking-status" role="status"><span className="thinking-dots"><i /><i /><i /></span>{pending}</p>}
            <form onSubmit={sendQuestion}><div className="composer-field"><label className="sr-only" htmlFor="question">Câu hỏi</label><textarea id="question" rows={2} maxLength={500} required disabled={busy} value={question} placeholder="Hỏi về tài liệu, quy định hay quy trình của đội ngũ..." onChange={(event) => setQuestion(event.target.value)} /><div className="composer-bottom"><span><Icon name="shield" size={13} />Tra cứu trong tài liệu được cấp quyền</span><div><small>{question.length}/500</small><button className="primary send-button" disabled={busy || !question.trim()}><span>Gửi</span><Icon name="send" size={16} /></button></div></div></div></form>
            <small className="composer-footnote">AI có thể sai. Hãy đối chiếu nguồn trước khi sử dụng. Sau lỗi kết nối, mở lại lịch sử trước khi gửi lại.</small>
          </footer>
        </>}
      </div>
    </main>
  </div>;
}
