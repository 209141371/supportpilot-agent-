from pathlib import Path


KNOWLEDGE_DIR = Path("data/knowledge")


def load_documents() -> list[dict]:
    documents = []

    for pattern in ("*.txt", "*.md"):
        for file_path in KNOWLEDGE_DIR.glob(pattern):
            content = file_path.read_text(encoding="utf-8")

            documents.append(
                {
                    "source": file_path.name,
                    "content": content,
                }
            )

    return documents


def split_text(
    text: str,
    chunk_size: int = 200,
    overlap: int = 40,
) -> list[str]:
    chunks = []

    start = 0

    while start < len(text):
        end = start + chunk_size

        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        start += chunk_size - overlap

    return chunks


def build_chunks() -> list[dict]:
    documents = load_documents()

    chunks = []

    for document in documents:
        paragraphs = split_by_paragraph(
            document["content"]
        )

        if not paragraphs:
            continue

        # 第一段作为文档标题
        title = paragraphs[0]

        # 后面的每个段落都带上标题
        body_paragraphs = paragraphs[1:]

        for index, paragraph in enumerate(body_paragraphs):
            chunk_content = (
                f"{title}\n\n"
                f"{paragraph}"
            )

            chunks.append(
                {
                    "id": f"{document['source']}-{index}",
                    "source": document["source"],
                    "content": chunk_content,
                }
            )

    return chunks
def split_by_paragraph(text: str) -> list[str]:
    paragraphs = []

    for paragraph in text.split("\n"):
        paragraph = paragraph.strip()

        if paragraph:
            paragraphs.append(paragraph)

    return paragraphs


if __name__ == "__main__":
    chunks = build_chunks()

    print(f"共生成 {len(chunks)} 个 chunks。\n")

    for chunk in chunks:
        print("=" * 50)
        print("ID:", chunk["id"])
        print("来源:", chunk["source"])
        print("内容:")
        print(chunk["content"])
        print()
