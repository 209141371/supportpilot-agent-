from agents import function_tool

from supportpilot.rag.retriever import search_knowledge_base as retrieve_knowledge


@function_tool
def search_knowledge_base(query: str) -> str:
    """从企业知识库中检索与用户问题最相关的政策内容。"""

    print(f"\n[Tool] 正在检索知识库：{query}")

    results = retrieve_knowledge(
        query=query,
        top_k=3,
    )

    if not results:
        return "知识库中未找到相关内容。"

    formatted_results = []

    for index, result in enumerate(results, start=1):
        formatted_results.append(
            f"[资料 {index}]\n"
            f"来源：{result['source']}\n"
            f"内容：{result['content']}"
        )

    output = "\n\n".join(formatted_results)

    print(f"[Tool] 找到 {len(results)} 条相关资料。")

    return output