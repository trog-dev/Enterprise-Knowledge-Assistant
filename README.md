# Enterprise Knowledge Assistant

Ứng dụng hỏi đáp tài liệu nội bộ bằng RAG. Quản trị viên tải tài liệu lên, xử lý và lập chỉ mục. Người dùng đặt câu hỏi bằng tiếng Việt, xem nguồn trích dẫn và mở lại lịch sử hội thoại.

## Chức năng

- Đọc TXT, PDF và Word `.docx`. PDF scan có thể được nhận dạng chữ bằng Tesseract với bộ ngôn ngữ Việt và Anh.
- Chia tài liệu thành đoạn, tạo embedding bằng `intfloat/multilingual-e5-small` và lưu vector vào Qdrant.
- Dùng Gemini để trả lời dựa trên các đoạn truy xuất được. Phản hồi đính kèm nguồn khi có đủ thông tin.
- Phân quyền tài liệu theo phạm vi quản trị viên, toàn công ty hoặc phòng ban. Quản trị viên quản lý tài liệu, nhân viên và phòng ban trên web.
- Lưu tài khoản, thông tin tài liệu và lịch sử hội thoại trong PostgreSQL.

## Yêu cầu chạy trên Windows

- Python 3.12, Node.js 22 kèm npm và Docker Desktop có Docker Compose.
- Gemini API key để chạy chức năng hỏi đáp.
- Tesseract OCR với dữ liệu ngôn ngữ `vie` và `eng` nếu cần xử lý PDF scan.

Mở PowerShell tại thư mục gốc của repo. Các khối lệnh dưới đây ghi rõ khi nào cần chuyển vào `backend` hoặc `frontend`.

## 1. Tạo cấu hình local

Với bản clone mới, sao chép cấu hình mẫu:

```powershell
Copy-Item .env.example .env
```

Mở `.env` ở thư mục gốc và đối chiếu các giá trị với `.env.example`:

| Biến | Giá trị cần đặt |
| --- | --- |
| `DATABASE_URL` | URL PostgreSQL với tên database, user và mật khẩu khớp `docker-compose.yml`. |
| `QDRANT_URL` | `http://localhost:6333` khi chạy Qdrant trên máy local. |
| `GEMINI_API_KEY` | API key của bạn. |
| `GEMINI_MODEL` | Model tạo văn bản có trong tài khoản Gemini của bạn. |
| `JWT_SECRET_KEY` | Chuỗi bí mật ngẫu nhiên ít nhất 32 ký tự. |
| `TESSERACT_CMD` | Đường dẫn tới `tesseract.exe` nếu dùng OCR. Ví dụ `C:/Program Files/Tesseract-OCR/tesseract.exe`. |
| `OCR_LANGUAGES` | `vie+eng` nếu đã cài cả hai bộ ngôn ngữ. |

Có thể tạo JWT secret bằng lệnh:

```powershell
py -3.12 -c "import secrets; print(secrets.token_urlsafe(48))"
```

## 2. Bật PostgreSQL và Qdrant

Từ thư mục gốc:

```powershell
docker compose up -d postgres qdrant
docker compose ps
```

Chờ PostgreSQL sẵn sàng trước khi chạy migration.

## 3. Cài và chạy backend

Từ thư mục gốc:

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Với database mới, tạo tài khoản quản trị bằng script trong repo. Xem hướng dẫn sử dụng trong `backend/scripts/create_admin.py` để biết tham số và cách nhập thông tin tài khoản của bản hiện tại. Chạy script bằng Python trong `backend\.venv` từ thư mục `backend`.

Khởi động API trong thư mục `backend` và giữ terminal này mở:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

- [Kiểm tra API](http://127.0.0.1:8001/health)
- [Swagger UI](http://127.0.0.1:8001/docs)

Lần đầu xử lý hoặc truy vấn, hệ thống có thể cần tải model embedding.

## 4. Cài và chạy frontend

Mở PowerShell thứ hai tại thư mục gốc:

```powershell
cd frontend
npm ci
npm run dev
```

Mở [http://localhost:5173](http://localhost:5173) hoặc địa chỉ Vite in ra. Trong chế độ phát triển, Vite chuyển yêu cầu `/api` đến backend tại `http://127.0.0.1:8001`.

## 5. Chạy thử

1. Đăng nhập bằng tài khoản quản trị.
2. Mở **Quản lý tài liệu**, tải một file mẫu, chọn phạm vi truy cập, xử lý và lập chỉ mục.
3. Mở **Trợ lý AI**, hỏi một câu có đáp án trong tài liệu và mở nguồn trích dẫn để đối chiếu.
4. Tạo nhân viên và phòng ban để thử phân quyền. Tài khoản nhân viên có thể xem tài liệu chia sẻ toàn công ty và tài liệu thuộc phòng ban của mình.

Dùng tài liệu giả lập nếu bạn định chia sẻ kết quả demo.

## Cấu trúc repo

```text
backend/
  app/api/          Các endpoint
  app/core/         Cấu hình và xác thực
  app/db/           Kết nối PostgreSQL
  app/models/       Mô hình dữ liệu
  app/services/     Đọc tài liệu, embedding, truy xuất và Gemini
  migrations/       Alembic migrations
  scripts/          Script quản trị và kiểm tra
  requirements.txt
frontend/
  src/              Giao diện React và mã gọi API
  public/           Tài nguyên tĩnh
docker-compose.yml  PostgreSQL và Qdrant cho môi trường local
.env.example        Mẫu cấu hình
```

## Dừng hệ thống

Nhấn `Ctrl+C` ở các terminal chạy API và frontend. Từ thư mục gốc, chạy:

```powershell
docker compose stop
```

Lệnh này giữ lại dữ liệu trong volume. Chạy lại `docker compose up -d postgres qdrant` khi cần tiếp tục.

Giữ `.env`, API key, mật khẩu, tài liệu nội bộ và bản sao dữ liệu ở ngoài Git. Các bước trên dùng để chạy local. Để mở web qua Internet, cần triển khai frontend và backend cùng các dịch vụ lưu trữ lên máy chủ.
