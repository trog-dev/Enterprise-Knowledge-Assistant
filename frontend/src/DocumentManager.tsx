import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { api, departmentName, getAll, jsonRequest } from "./api";
import type { AccessScope, Department, DocumentItem, ProcessResponse, Profile } from "./api";
import Icon from "./Icon";
import Stats from "./Stats";
import { useOperation } from "./useOperation";
import type { ScreenProps } from "./useOperation";

const scopeLabels: Record<AccessScope, string> = {
  admin_only: "Chỉ admin", company: "Toàn công ty", department: "Riêng phòng ban",
};
const statusLabels: Record<string, string> = {
  uploaded: "Đã tải lên", chunked: "Đã chia đoạn", indexed: "Sẵn sàng tìm kiếm",
};
function fileSize(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function PermissionFields({ prefix, scope, department, departments, disabled, onScope, onDepartment }: {
  prefix: string; scope: AccessScope; department: string; departments: Department[];
  disabled: boolean; onScope: (value: AccessScope) => void; onDepartment: (value: string) => void;
}) {
  return <div className="permission-fields">
    <label htmlFor={`${prefix}-scope`}>Phạm vi truy cập</label>
    <select id={`${prefix}-scope`} value={scope} disabled={disabled}
      onChange={(event) => onScope(event.target.value as AccessScope)}>
      <option value="admin_only">Chỉ admin</option>
      <option value="company">Toàn công ty</option>
      <option value="department">Riêng phòng ban</option>
    </select>
    {scope === "department" && <>
      <label htmlFor={`${prefix}-department`}>Phòng ban được đọc</label>
      <select id={`${prefix}-department`} value={department} disabled={disabled} required
        onChange={(event) => onDepartment(event.target.value)}>
        <option value="">Chọn phòng ban</option>
        {departments.map((item) => <option key={item.id} value={item.id}>{item.name} ({item.code})</option>)}
      </select>
      {departments.length === 0 && <small className="muted">Tạo phòng ban ở màn hình Nhân viên trước.</small>}
    </>}
  </div>;
}

function PermissionEditor({ document, departments, busy, onSave }: {
  document: DocumentItem; departments: Department[]; busy: boolean;
  onSave: (scope: AccessScope, departmentId: number | null) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [scope, setScope] = useState<AccessScope>(document.access_scope);
  const [department, setDepartment] = useState(document.department_id?.toString() ?? "");
  const selectedId = scope === "department" && department ? Number(department) : null;
  const changed = scope !== document.access_scope || selectedId !== document.department_id;
  if (!editing) return <div className="access-summary"><span className={`access-pill access-${document.access_scope}`}><Icon name={document.access_scope === "admin_only" ? "lock" : document.access_scope === "company" ? "building" : "users"} size={12} />{scopeLabels[document.access_scope]}</span>
    {document.access_scope === "department" && <small>{departmentName(document.department_id, departments)}</small>}
    <button type="button" className="permission-edit" disabled={busy} onClick={() => setEditing(true)}>Chỉnh quyền</button>
  </div>;
  return <form className="permission-editor" onSubmit={(event) => {
    event.preventDefault();
    if (!busy && changed && (scope !== "department" || selectedId !== null)) onSave(scope, selectedId);
  }}>
    <PermissionFields prefix={`document-${document.id}`} scope={scope} department={department}
      departments={departments} disabled={busy} onDepartment={setDepartment}
      onScope={(value) => { setScope(value); if (value !== "department") setDepartment(""); }} />
    <button type="submit" disabled={busy || !changed || (scope === "department" && !department)}>
      Lưu quyền
    </button>
    <button type="button" className="cancel-edit" disabled={busy} onClick={() => {
      setScope(document.access_scope); setDepartment(document.department_id?.toString() ?? ""); setEditing(false);
    }}>Hủy</button>
  </form>;
}

export default function DocumentManager({ token, user, onBusyChange, onSessionExpired }: ScreenProps & { user: Profile }) {
  const isAdmin = user.role === "admin";
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [uploadScope, setUploadScope] = useState<AccessScope>("admin_only");
  const [uploadDepartment, setUploadDepartment] = useState("");
  const [forceOcr, setForceOcr] = useState(false);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [dragging, setDragging] = useState(false);
  const [notice, setNotice] = useState("");
  const [warnings, setWarnings] = useState<string[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const { run, pending, busy, error, setError } = useOperation(onBusyChange, onSessionExpired);

  useEffect(() => {
    void run("Đang tải tài liệu...", async () => {
      const [items, groups] = await Promise.all([
        getAll<DocumentItem>("/documents", token),
        isAdmin ? getAll<Department>("/auth/departments", token) : Promise.resolve([] as Department[]),
      ]);
      setDocuments(items); setDepartments(groups);
    });
  }, [token, isAdmin, run]);

  async function reload() {
    const [items, groups] = await Promise.all([
      getAll<DocumentItem>("/documents", token),
      isAdmin ? getAll<Department>("/auth/departments", token) : Promise.resolve([] as Department[]),
    ]);
    setDocuments(items); setDepartments(groups);
  }

  function action(label: string, task: () => Promise<string>) {
    setNotice(""); setWarnings([]);
    return run(label, async () => {
      const message = await task();
      setNotice(message);
      // The success notice remains visible if refreshing the list fails.
      await reload();
    });
  }

  function selectFile(selected: File | null) {
    if (busy) return;
    setError("");
    if (selected && (!/\.(txt|pdf|docx)$/i.test(selected.name.trim()) || selected.size === 0 || selected.size > 20 * 1024 * 1024)) {
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
      setError("Chọn file TXT, PDF hoặc DOCX có nội dung và không vượt quá 20 MB.");
      return;
    }
    setFile(selected);
  }

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!isAdmin || !file || busy) return;
    if (!/\.(txt|pdf|docx)$/i.test(file.name.trim())) { setError("Chỉ nhận TXT, PDF hoặc DOCX."); return; }
    if (file.size === 0 || file.size > 20 * 1024 * 1024) { setError("File phải có nội dung và không vượt quá 20 MB."); return; }
    if (uploadScope === "department" && !uploadDepartment) { setError("Hãy chọn phòng ban được đọc."); return; }
    const selected = file;
    await action("Đang tải tài liệu lên...", async () => {
      const form = new FormData();
      form.append("file", selected);
      form.append("access_scope", uploadScope);
      if (uploadScope === "department") form.append("department_id", uploadDepartment);
      await api<DocumentItem>("/documents", token, { method: "POST", body: form });
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
      return `Đã tải lên ${selected.name}. Tiếp theo: Chia đoạn → Tạo chỉ mục.`;
    });
  }

  async function process(document: DocumentItem) {
    if (!isAdmin) return;
    const ocr = forceOcr && /\.pdf$/i.test(document.original_name.trim());
    await action(`Đang xử lý ${document.original_name}...`, async () => {
      const result = await api<ProcessResponse>(`/documents/${document.id}/process?force_ocr=${ocr}`, token, { method: "POST" });
      setWarnings(result.warnings ?? []);
      return `Đã tạo ${result.chunk_count} đoạn cho ${document.original_name}. Tiếp theo: Tạo chỉ mục.`;
    });
  }

  async function index(document: DocumentItem) {
    if (!isAdmin) return;
    await action(`Đang tạo chỉ mục ${document.original_name}...`, async () => {
      await api<unknown>(`/documents/${document.id}/index`, token, { method: "POST" });
      return `${document.original_name} đã sẵn sàng tìm kiếm.`;
    });
  }

  async function savePermissions(document: DocumentItem, scope: AccessScope, departmentId: number | null) {
    if (!isAdmin) return;
    await action(`Đang lưu quyền ${document.original_name}...`, async () => {
      await api<DocumentItem>(`/documents/${document.id}/permissions`, token, jsonRequest("PATCH", {
        access_scope: scope, department_id: scope === "department" ? departmentId : null,
      }));
      return `Đã cập nhật quyền ${document.original_name}. Không cần tạo lại vector.`;
    });
  }

  const visibleDocuments = documents.filter((document) =>
    document.original_name.toLocaleLowerCase("vi").includes(query.toLocaleLowerCase("vi")) &&
    (!statusFilter || document.status === statusFilter)
  );

  return <section className="management-page documents-page">
    <header className="page-heading"><div><p className="eyebrow">QUẢN LÝ TRI THỨC</p>
      <h1>{isAdmin ? "Quản lý tài liệu" : "Tài liệu được phép đọc"}</h1>
      <p>{isAdmin ? "Chọn phạm vi truy cập và chuẩn bị tài liệu cho hỏi đáp." : "Danh sách này chỉ chứa tài liệu tài khoản của bạn được phép xem."}</p>
    </div><button disabled={busy} onClick={() => action("Đang làm mới...", async () => "Đã cập nhật danh sách.")}><Icon name="refresh" size={16} />Làm mới</button></header>

    <Stats items={[
      { label: "Tổng tài liệu", value: documents.length, detail: "Trong phạm vi tài khoản", icon: "documents", tone: "blue" },
      { label: "Sẵn sàng tra cứu", value: documents.filter((item) => item.status === "indexed").length, detail: "Đã lập chỉ mục tìm kiếm", icon: "check", tone: "teal" },
      { label: "Chờ xử lý", value: documents.filter((item) => ["uploaded", "chunked"].includes(item.status)).length, detail: "Cần xử lý hoặc tạo chỉ mục", icon: "clock", tone: "amber" },
      { label: "Theo phòng ban", value: documents.filter((item) => item.access_scope === "department").length, detail: "Có phạm vi chia sẻ theo nhóm", icon: "shield", tone: "violet" },
    ]} />
    {isAdmin && <details className="creation-panel"><summary><span className="create-summary-icon"><Icon name="upload" size={19} /></span><span><strong>Thêm tài liệu</strong><small>Tải nguồn mới và chọn người được phép truy cập.</small></span><span className="create-summary-action"><span className="when-closed">Mở biểu mẫu</span><span className="when-open">Thu gọn</span><Icon name="plus" size={17} /></span></summary><div className="management-grid document-upload-grid">
      <form className="card upload-card" onSubmit={upload}><div className="card-heading"><span className="card-heading-icon tone-teal"><Icon name="upload" size={20} /></span><div><h2>Tải tài liệu mới</h2><p>Thêm nguồn tri thức cho đội ngũ của bạn.</p></div></div>
        <label htmlFor="document-file">File tài liệu</label>
        <div className={`drop-zone ${dragging ? "drag-active" : ""} ${file ? "has-file" : ""}`}
          onDragOver={(event) => { event.preventDefault(); if (!busy) setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => { event.preventDefault(); setDragging(false); selectFile(event.dataTransfer.files?.[0] ?? null); }}>
          <input ref={inputRef} id="document-file" className="file-input-overlay" type="file" accept=".txt,.pdf,.docx" disabled={busy}
            onChange={(event) => selectFile(event.target.files?.[0] ?? null)} />
          <span className="drop-icon"><Icon name={file ? "documents" : "upload"} size={25} /></span>
          <strong>{file ? file.name : "Chọn file hoặc kéo thả vào đây"}</strong>
          <span>{file ? fileSize(file.size) : "PDF, Word DOCX hoặc TXT · Tối đa 20 MB"}</span>
          <div className="file-type-badges" aria-hidden="true"><span>PDF</span><span>DOCX</span><span>TXT</span></div>
        </div>
        <p className="muted upload-hint">TXT cần UTF-8. Word .doc cần chuyển sang .docx.</p>
        <PermissionFields prefix="upload" scope={uploadScope} department={uploadDepartment} departments={departments}
          disabled={busy} onDepartment={setUploadDepartment}
          onScope={(value) => { setUploadScope(value); if (value !== "department") setUploadDepartment(""); }} />
        <button className="primary" type="submit" disabled={busy || !file || (uploadScope === "department" && !uploadDepartment)}><Icon name="upload" size={16} />Tải lên</button>
      </form>
      <div className="card processing-card"><div className="card-heading"><span className="card-heading-icon tone-blue"><Icon name="shield" size={20} /></span><div><h2>Chuẩn bị để tra cứu</h2><p>Mỗi tài liệu được xử lý theo ba bước.</p></div></div>
        <ol className="steps"><li>Tải tài liệu và chọn người được đọc.</li><li>Nhấn Chia đoạn để trích xuất nội dung.</li><li>Nhấn Tạo chỉ mục để đưa vào tìm kiếm.</li></ol>
        <label className="checkbox-label"><input type="checkbox" checked={forceOcr} disabled={busy}
          onChange={(event) => setForceOcr(event.target.checked)} />OCR toàn bộ trang PDF khi chia đoạn</label>
        <p className="muted">Tắt với PDF có chữ bình thường. Bật cho scan hoặc PDF có lớp chữ lỗi. OCR cần Tesseract trên backend và có thể mất nhiều thời gian.</p>
        <p className="info-box"><Icon name="shield" size={17} />Đổi quyền trong bảng có hiệu lực ở request tiếp theo; không cần tạo lại vector. Tài liệu mới mặc định chỉ admin đọc được.</p>
      </div>
    </div></details>}

    {pending && <p className="notice" role="status">{pending}</p>}
    {error && <p className="error" role="alert">{error}</p>}
    {notice && <p className="success" role="status">{notice}</p>}
    {warnings.length > 0 && <div className="warning"><strong>Lưu ý khi đọc tài liệu</strong><ul>{warnings.map((item, i) => <li key={i}>{item}</li>)}</ul></div>}
    <div className="data-panel">
    <div className="list-heading"><div><h2>Danh sách tài liệu <span className="count-pill">{documents.length}</span></h2><p>Quản lý trạng thái và quyền truy cập trong cùng một nơi.</p></div></div>
    <div className="table-toolbar"><div className="search-field"><Icon name="search" size={17} /><input aria-label="Tìm tài liệu" placeholder="Tìm theo tên tài liệu..." value={query} onChange={(event) => setQuery(event.target.value)} /></div>
      <select aria-label="Lọc trạng thái tài liệu" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="">Tất cả trạng thái</option><option value="uploaded">Đã tải lên</option><option value="chunked">Đã chia đoạn</option><option value="indexed">Sẵn sàng tìm kiếm</option></select>
    </div>
    <p className="mobile-table-hint">Vuốt ngang bảng để xem đầy đủ các cột.</p>
    <div className="table-scroll"><table><thead><tr><th>Tài liệu</th><th>Trạng thái</th><th>Quyền truy cập</th>{isAdmin && <th>Thao tác</th>}</tr></thead><tbody>
      {visibleDocuments.length === 0 && <tr><td colSpan={isAdmin ? 4 : 3} className="empty-cell">{busy ? "Đang tải..." : documents.length > 0 ? "Không tìm thấy tài liệu phù hợp bộ lọc." : "Chưa có tài liệu được phép xem."}</td></tr>}
      {visibleDocuments.map((document) => <tr key={document.id}>
        <td><div className="file-cell"><span className={`table-file-icon file-${document.original_name.split(".").pop()?.toLowerCase()}`}><Icon name="documents" size={21} /></span><div><strong className="document-name">{document.original_name}</strong><small className="muted block">#{document.id} · {fileSize(document.file_size)}</small><small className="muted block">{new Date(document.created_at).toLocaleString("vi-VN")}</small></div></div></td>
        <td><span className={`badge status-${document.status}`}>{statusLabels[document.status] ?? document.status}</span></td>
        <td>{isAdmin ? <PermissionEditor key={`${document.id}-${document.access_scope}-${document.department_id}`}
          document={document} departments={departments} busy={busy}
          onSave={(scope, id) => { void savePermissions(document, scope, id); }} /> : <>
          <span>{scopeLabels[document.access_scope] ?? "Theo quyền tài khoản"}</span>
          {document.access_scope === "department" && <small className="muted block">{departmentName(document.department_id, departments)}</small>}
        </>}</td>
        {isAdmin && <td><div className="row-actions">
          <button disabled={busy || document.status !== "uploaded" || !/\.(txt|pdf|docx)$/i.test(document.original_name.trim())} onClick={() => process(document)}>Chia đoạn</button>
          <button disabled={busy || !["chunked", "indexed"].includes(document.status)} onClick={() => index(document)}>{document.status === "indexed" ? "Ghi lại vector" : "Tạo chỉ mục"}</button>
        </div></td>}
      </tr>)}
    </tbody></table></div>
    <div className="table-footer"><span>{visibleDocuments.length} / {documents.length} tài liệu</span><span><Icon name="shield" size={13} />Hiển thị theo quyền tài khoản</span></div>
    </div>
  </section>;
}
