export interface Profile {
  id: number;
  email: string;
  full_name: string;
  role: "admin" | "employee";
  is_active: boolean;
  department_id: number | null;
}

export interface Department {
  id: number;
  code: string;
  name: string;
}

export type AccessScope = "admin_only" | "company" | "department";

export interface DocumentItem {
  id: number;
  original_name: string;
  file_size: number;
  status: string;
  uploaded_by: number;
  created_at: string;
  access_scope: AccessScope;
  department_id: number | null;
}

export interface Citation {
  source_id: string;
  chunk_id: number;
  document_id: number;
  document_name: string;
  chunk_index: number;
  content: string;
  page_number?: number | null;
  source_location?: string | null;
}

export interface Conversation { id: number; title: string; created_at: string }
export interface Turn {
  id: number;
  conversation_id: number;
  question: string;
  answer: string;
  sufficient: boolean;
  sources: Citation[];
}
export interface ChatResponse {
  question: string;
  answer: string;
  sufficient: boolean;
  sources: Citation[];
  conversation_id: number;
  turn_id: number;
}
export interface TokenResponse { access_token: string; token_type: string }
export interface ProcessResponse {
  document_id: number;
  status: string;
  chunk_count: number;
  warnings?: string[];
  ocr_pages?: number[];
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

function detailMessage(body: unknown, fallback: string): string {
  if (!body || typeof body !== "object" || !("detail" in body)) return fallback;
  const detail = (body as { detail: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail.map((item: unknown) => {
      if (item && typeof item === "object" && "msg" in item) return String(item.msg);
      return "Dữ liệu gửi lên không hợp lệ";
    });
    return messages.join("; ");
  }
  return fallback;
}

export async function api<T>(
  path: string, token: string | null, options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let response: Response;
  try {
    response = await fetch(`/api${path}`, { ...options, headers });
  } catch {
    throw new Error("Không kết nối được máy chủ. Kiểm tra backend cổng 8001. Nếu vừa gửi dữ liệu, làm mới để kiểm tra trước khi gửi lại.");
  }
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    throw new ApiError(response.status, detailMessage(body, `Yêu cầu thất bại: HTTP ${response.status}`));
  }
  return await response.json() as T;
}

export async function getAll<T>(path: string, token: string): Promise<T[]> {
  const items: T[] = [];
  const limit = 100;
  for (let offset = 0; ; offset += limit) {
    const page = await api<T[]>(`${path}?offset=${offset}&limit=${limit}`, token);
    items.push(...page);
    if (page.length < limit) return items;
  }
}

export function jsonRequest(method: string, body: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

export function departmentName(id: number | null, departments: Department[]): string {
  if (id == null) return "Chưa gán phòng ban";
  return departments.find((item) => item.id === id)?.name ?? `Phòng ban #${id}`;
}
