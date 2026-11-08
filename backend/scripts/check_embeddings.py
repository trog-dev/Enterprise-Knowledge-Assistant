import sys

from app.services.embeddings import embed_passages, embed_query

sys.stdout.reconfigure(encoding="utf-8")

passages = [
    "Nhân viên được hưởng 12 ngày nghỉ phép mỗi năm.",
    "Nhân viên cần gửi yêu cầu nghỉ trước 3 ngày làm việc.",
    "Máy tính cần được cập nhật phần mềm định kỳ.",
]

question = "Mỗi năm tôi có bao nhiêu ngày phép?"

# Hiển thị dạng ASCII để phân biệt lỗi dữ liệu với lỗi hiển thị.
print("Input check:", ascii(passages[0]))

if any("?" in passage or "\ufffd" in passage for passage in passages):
    raise ValueError("Văn bản mẫu đã bị lỗi mã hóa")

passage_vectors = embed_passages(passages)
question_vector = embed_query(question)

scores = [
    sum(a * b for a, b in zip(question_vector, vector))
    for vector in passage_vectors
]

print("\nQuestion:", question)
print("Vector size:", len(question_vector))
print("\nRanking:")

for index in sorted(
    range(len(scores)),
    key=lambda i: scores[i],
    reverse=True,
):
    print(f"{scores[index]:.4f} | {passages[index]}")