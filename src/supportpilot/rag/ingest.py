import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from supportpilot.rag.chunker import build_chunks


CHROMA_PATH = "data/chroma"
COLLECTION_NAME = "supportpilot_knowledge"
EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"


def create_embedding_function():
    return SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL,
    )


def ingest_knowledge_base():
    chunks = build_chunks()

    client = chromadb.PersistentClient(
        path=CHROMA_PATH,
    )

    embedding_function = create_embedding_function()

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_function,
    )

    ids = [chunk["id"] for chunk in chunks]

    documents = [
        chunk["content"]
        for chunk in chunks
    ]

    metadatas = [
        {
            "source": chunk["source"],
        }
        for chunk in chunks
    ]

    collection.upsert(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
    )

    print(f"已写入 {len(chunks)} 个 chunks。")
    print(f"Embedding 模型：{EMBEDDING_MODEL}")
    print(f"ChromaDB 路径：{CHROMA_PATH}")


if __name__ == "__main__":
    ingest_knowledge_base()