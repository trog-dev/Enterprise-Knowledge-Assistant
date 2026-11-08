import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api, departmentName, getAll, jsonRequest } from "./api";
import type { Department, Profile } from "./api";
import Icon from "./Icon";
import Stats from "./Stats";
import { useOperation } from "./useOperation";
import type { ScreenProps } from "./useOperation";

function EmployeeEditor({ employee, departments, busy, onSave }: {
  employee: Profile; departments: Department[]; busy: boolean;
  onSave: (changes: { department_id?: number | null; is_active?: boolean }) => void;
}) {
  const [department, setDepartment] = useState(employee.department_id?.toString() ?? "");
  const [active, setActive] = useState(employee.is_active);
  const id = department ? Number(department) : null;
  const changed = id !== employee.department_id || active !== employee.is_active;
  return <form className="employee-editor" onSubmit={(event) => {
    event.preventDefault();
    if (busy || !changed) return;
    const changes: { department_id?: number | null; is_active?: boolean } = {};
    if (id !== employee.department_id) changes.department_id = id;
    if (active !== employee.is_active) changes.is_active = active;
    onSave(changes);
  }}>
    <label className="sr-only" htmlFor={`employee-${employee.id}-department`}>Phòng ban của {employee.email}</label>
    <select id={`employee-${employee.id}-department`} value={department} disabled={busy}
      onChange={(event) => setDepartment(event.target.value)}>
      <option value="">Chưa gán phòng ban</option>
      {departments.map((item) => <option key={item.id} value={item.id}>{item.name} ({item.code})</option>)}
    </select>
    <label className="checkbox-label"><input type="checkbox" checked={active} disabled={busy}
      aria-label={`Hoạt động: ${employee.email}`} onChange={(event) => setActive(event.target.checked)} />Cho phép đăng nhập</label>
    <button type="submit" disabled={busy || !changed}>Lưu thay đổi</button>
  </form>;
}

export default function UserManager({ token, user, onBusyChange, onSessionExpired }: ScreenProps & { user: Profile }) {
  const [departments, setDepartments] = useState<Department[]>([]);
  const [users, setUsers] = useState<Profile[]>([]);
  const [code, setCode] = useState("");
  const [departmentLabel, setDepartmentLabel] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [newDepartment, setNewDepartment] = useState("");
  const [notice, setNotice] = useState("");
  const [query, setQuery] = useState("");
  const [activeFilter, setActiveFilter] = useState("");
  const [departmentFilter, setDepartmentFilter] = useState("");
  const { run, pending, busy, error } = useOperation(onBusyChange, onSessionExpired);
  const isAdmin = user.role === "admin";

  useEffect(() => {
    if (!isAdmin) return;
    void run("Đang tải nhân viên và phòng ban...", async () => {
      const [groups, people] = await Promise.all([
        getAll<Department>("/auth/departments", token), getAll<Profile>("/auth/users", token),
      ]);
      setDepartments(groups); setUsers(people);
    });
  }, [token, isAdmin, run]);

  async function reload() {
    const [groups, people] = await Promise.all([
      getAll<Department>("/auth/departments", token), getAll<Profile>("/auth/users", token),
    ]);
    setDepartments(groups); setUsers(people);
  }

  function action(label: string, task: () => Promise<string>) {
    if (!isAdmin) return;
    setNotice("");
    return run(label, async () => {
      const message = await task();
      setNotice(message);
      await reload();
    });
  }

  async function createDepartment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await action("Đang tạo phòng ban...", async () => {
      const created = await api<Department>("/auth/departments", token, jsonRequest("POST", {
        code: code.trim().toUpperCase(), name: departmentLabel.trim(),
      }));
      setCode(""); setDepartmentLabel("");
      return `Đã tạo phòng ${created.name} (${created.code}).`;
    });
  }

  async function createEmployee(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await action("Đang tạo nhân viên...", async () => {
      const created = await api<Profile>("/auth/users", token, jsonRequest("POST", {
        email: email.trim().toLowerCase(), full_name: name.trim(), password,
        role: "employee", department_id: newDepartment ? Number(newDepartment) : null,
      }));
      setName(""); setEmail(""); setPassword(""); setNewDepartment("");
      return `Đã tạo nhân viên ${created.email}. Hãy cung cấp mật khẩu cho đúng người qua kênh phù hợp.`;
    });
  }

  if (!isAdmin) return <section className="management-page"><p className="error" role="alert">Chỉ admin được quản lý nhân viên.</p></section>;

  const visibleUsers = users.filter((employee) => {
    const matchesQuery = `${employee.full_name} ${employee.email}`.toLocaleLowerCase("vi").includes(query.toLocaleLowerCase("vi"));
    const matchesActive = !activeFilter || (activeFilter === "active" ? employee.is_active : !employee.is_active);
    const matchesDepartment = !departmentFilter || (departmentFilter === "none" ? employee.department_id == null : employee.department_id === Number(departmentFilter));
    return matchesQuery && matchesActive && matchesDepartment;
  });

  return <section className="management-page users-page">
    <header className="page-heading"><div><p className="eyebrow">QUẢN TRỊ</p><h1>Nhân viên & phòng ban</h1><p>Tạo nhân viên, chuyển phòng và kiểm soát trạng thái tài khoản.</p></div>
      <button disabled={busy} onClick={() => action("Đang làm mới...", async () => "Đã cập nhật danh sách.")}><Icon name="refresh" size={16} />Làm mới</button>
    </header>
    <Stats items={[
      { label: "Tổng tài khoản", value: users.length, detail: "Admin và nhân viên", icon: "users", tone: "blue" },
      { label: "Đang hoạt động", value: users.filter((item) => item.is_active).length, detail: "Được phép đăng nhập", icon: "check", tone: "teal" },
      { label: "Phòng ban", value: departments.length, detail: "Nhóm làm việc trong hệ thống", icon: "building", tone: "violet" },
      { label: "Tài khoản đã khóa", value: users.filter((item) => !item.is_active).length, detail: "Tạm ngừng quyền truy cập", icon: "lock", tone: "amber" },
    ]} />
    <details className="creation-panel"><summary><span className="create-summary-icon"><Icon name="users" size={19} /></span><span><strong>Thêm nhân viên hoặc phòng ban</strong><small>Tạo tài khoản mới và tổ chức đội ngũ.</small></span><span className="create-summary-action"><span className="when-closed">Mở biểu mẫu</span><span className="when-open">Thu gọn</span><Icon name="plus" size={17} /></span></summary><div className="management-grid user-form-grid">
      <form className="card" onSubmit={createEmployee}><div className="card-heading"><span className="card-heading-icon tone-teal"><Icon name="users" size={20} /></span><div><h2>Tạo nhân viên</h2><p>Cấp tài khoản và gán phòng ban cho thành viên.</p></div></div>
        <label htmlFor="employee-name">Họ tên</label><input id="employee-name" value={name} disabled={busy} required maxLength={150}
          onChange={(event) => setName(event.target.value)} />
        <label htmlFor="employee-email">Email nhân viên</label><input id="employee-email" type="email" value={email} disabled={busy} required maxLength={255} autoComplete="off"
          onChange={(event) => setEmail(event.target.value)} />
        <label htmlFor="employee-password">Mật khẩu ban đầu</label><input id="employee-password" type="password" value={password} disabled={busy} required minLength={12} maxLength={128} autoComplete="new-password"
          onChange={(event) => setPassword(event.target.value)} />
        <small className="muted block">Từ 12 đến 128 ký tự. Mật khẩu không được hiển thị trong danh sách tài khoản.</small>
        <label htmlFor="employee-department">Phòng ban nhân viên</label><select id="employee-department" value={newDepartment} disabled={busy}
          onChange={(event) => setNewDepartment(event.target.value)}><option value="">Chưa gán phòng ban</option>
          {departments.map((item) => <option key={item.id} value={item.id}>{item.name} ({item.code})</option>)}</select>
        <p className="muted">Nhân viên chưa có phòng ban chỉ đọc được tài liệu toàn công ty.</p>
        <button className="primary" type="submit" disabled={busy || !name.trim() || !email.trim() || password.length < 12}><Icon name="plus" size={16} />Tạo nhân viên</button>
      </form>
      <div className="card department-card"><form onSubmit={createDepartment}><div className="card-heading"><span className="card-heading-icon tone-violet"><Icon name="building" size={20} /></span><div><h2>Tạo phòng ban</h2><p>Tổ chức đội ngũ theo nhóm truy cập.</p></div></div>
        <label htmlFor="department-code">Mã phòng ban</label><input id="department-code" value={code} required minLength={2} maxLength={20} pattern="[A-Z][A-Z0-9_]+" disabled={busy}
          placeholder="Ví dụ: HR, IT, SALES" onChange={(event) => setCode(event.target.value.toUpperCase())} />
        <label htmlFor="department-name">Tên phòng ban</label><input id="department-name" value={departmentLabel} required maxLength={150} disabled={busy}
          onChange={(event) => setDepartmentLabel(event.target.value)} />
        <button className="primary" type="submit" disabled={busy || code.trim().length < 2 || !departmentLabel.trim()}><Icon name="plus" size={16} />Tạo phòng ban</button>
      </form>
      <div className="department-list"><h3>Phòng ban hiện có</h3>
        {departments.length === 0 ? <p className="muted">Chưa có phòng ban.</p> : <ul>{departments.map((item) => <li key={item.id}><strong>{item.code}</strong><span>{item.name}</span></li>)}</ul>}
      </div></div>
    </div></details>
    {pending && <p className="notice" role="status">{pending}</p>}
    {error && <p className="error" role="alert">{error}</p>}
    {notice && <p className="success" role="status">{notice}</p>}
    <div className="data-panel">
    <div className="list-heading"><div><h2>Danh sách tài khoản <span className="count-pill">{users.length}</span></h2><p>Thay phòng hoặc khóa nhân viên có hiệu lực ở request tiếp theo.</p></div><span className="protected-label"><Icon name="shield" size={14} />Admin được bảo vệ</span></div>
    <div className="table-toolbar"><div className="search-field"><Icon name="search" size={17} /><input aria-label="Tìm nhân viên" placeholder="Tìm theo tên hoặc email..." value={query} onChange={(event) => setQuery(event.target.value)} /></div>
      <select aria-label="Lọc phòng ban nhân viên" value={departmentFilter} onChange={(event) => setDepartmentFilter(event.target.value)}><option value="">Tất cả phòng ban</option><option value="none">Chưa gán phòng ban</option>{departments.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
      <select aria-label="Lọc trạng thái tài khoản" value={activeFilter} onChange={(event) => setActiveFilter(event.target.value)}><option value="">Tất cả trạng thái</option><option value="active">Đang hoạt động</option><option value="locked">Đã khóa</option></select>
    </div>
    <p className="mobile-table-hint">Vuốt ngang bảng để xem đầy đủ các cột.</p>
    <div className="table-scroll"><table><thead><tr><th>Nhân viên</th><th>Vai trò</th><th>Hiện tại</th><th>Cập nhật quyền truy cập</th></tr></thead><tbody>
      {visibleUsers.length === 0 && <tr><td colSpan={4} className="empty-cell">{busy ? "Đang tải..." : users.length > 0 ? "Không có tài khoản phù hợp bộ lọc." : "Chưa có tài khoản."}</td></tr>}
      {visibleUsers.map((employee) => <tr key={employee.id}>
        <td><div className="employee-cell"><span className={`employee-avatar ${employee.role === "admin" ? "avatar-admin" : ""}`}>{employee.full_name.split(/\s+/).filter(Boolean).map((part) => part[0]).slice(0, 2).join("").toUpperCase()}</span><div><strong>{employee.full_name}</strong><small className="muted block">{employee.email}</small>{employee.id === user.id && <small className="own-account">Tài khoản của bạn</small>}</div></div></td>
        <td><span className={`badge role-${employee.role}`}>{employee.role === "admin" ? "Admin" : "Nhân viên"}</span></td>
        <td><span className={`badge ${employee.is_active ? "status-indexed" : "status-locked"}`}>{employee.is_active ? "Đang hoạt động" : "Đã khóa"}</span><small className="muted block">{departmentName(employee.department_id, departments)}</small></td>
        <td>{employee.role === "admin" ? <span className="protected-account"><Icon name="shield" size={16} />Tài khoản quản trị được bảo vệ.</span> : <EmployeeEditor
          key={`${employee.id}-${employee.department_id}-${employee.is_active}`} employee={employee} departments={departments} busy={busy}
          onSave={(changes) => { void action(`Đang cập nhật ${employee.email}...`, async () => {
            await api<Profile>(`/auth/users/${employee.id}`, token, jsonRequest("PATCH", changes));
            return `Đã cập nhật ${employee.email}.`;
          }); }} />}</td>
      </tr>)}
    </tbody></table></div>
    <div className="table-footer"><span>{visibleUsers.length} / {users.length} tài khoản</span><span><Icon name="shield" size={13} />Quản trị truy cập theo tài khoản</span></div>
    </div>
  </section>;
}
