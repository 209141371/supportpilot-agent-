import asyncio
import json
import re
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from agents import Runner
from agents.stream_events import RawResponsesStreamEvent, RunItemStreamEvent

from supportpilot.agent import create_support_agent
from supportpilot.auth import (
    create_access_token,
    current_user,
    hash_password,
    require_roles,
    verify_password,
)
from supportpilot.db import (
    count_users,
    create_approval_request,
    create_ticket_in_db,
    create_user,
    get_approval_request,
    get_order_from_db,
    get_ticket_from_db,
    get_user_by_email,
    init_db,
    list_approval_requests,
    list_conversation_messages,
    list_conversations,
    list_knowledge_documents,
    list_orders_from_db,
    list_tickets_from_db,
    save_knowledge_document,
    save_message,
    update_approval_request,
    update_ticket_status_in_db,
)
from supportpilot.rag.chunker import build_chunks
from supportpilot.rag.ingest import ingest_knowledge_base
from supportpilot.services.chat_service import (
    find_approval_request,
    process_chat_message,
)
from supportpilot.workflows.shipping_workflow import (
    ShippingWorkflowState,
    approve_shipping_ticket,
    reject_shipping_ticket,
    run_shipping_workflow,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
KNOWLEDGE_DIR = PROJECT_ROOT / "data" / "knowledge"
EVAL_REPORT_PATH = PROJECT_ROOT / "evals" / "eval_report.md"
LOG_DIR = PROJECT_ROOT / "data" / "logs"
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


class RegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=160)
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=80)


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=160)
    password: str = Field(min_length=1, max_length=128)


class CreateUserRequest(BaseModel):
    email: str = Field(min_length=5, max_length=160)
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=80)
    role: str = Field(pattern="^(agent|supervisor|admin)$")


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    request_id: str
    session_id: str
    answer: str
    approval_required: bool
    approval_id: str | None = None
    approval_request: dict[str, str] | None = None


class TicketCreateRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    order_id: str = Field(min_length=1, max_length=30)
    issue_type: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=1000)


class ApprovalDecisionRequest(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")


class ShippingWorkflowRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    order_id: str = Field(min_length=1, max_length=30)


app = FastAPI(title="SupportPilot API", version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "supportpilot-api"}


@app.post("/api/auth/register")
def register(request: RegisterRequest) -> dict:
    """只允许在没有用户时开放首个管理员注册。"""

    if count_users() > 0:
        raise HTTPException(status_code=403, detail="系统已有用户，请联系管理员创建账号")

    if get_user_by_email(request.email) is not None:
        raise HTTPException(status_code=409, detail="邮箱已注册")

    user = create_user(
        email=request.email,
        password_hash=hash_password(request.password),
        display_name=request.display_name,
        role="admin",
    )
    return {"access_token": create_access_token(user), "token_type": "bearer", "user": user}


@app.post("/api/auth/login")
def login(request: LoginRequest) -> dict:
    user = get_user_by_email(request.email)
    if user is None or not user["is_active"] or not verify_password(request.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

    public_user = {key: value for key, value in user.items() if key not in {"password_hash", "is_active"}}
    return {"access_token": create_access_token(user), "token_type": "bearer", "user": public_user}


@app.post("/api/auth/users")
def create_managed_user(
    request: CreateUserRequest,
    user: dict = Depends(require_roles("admin")),
) -> dict:
    if get_user_by_email(request.email) is not None:
        raise HTTPException(status_code=409, detail="邮箱已注册")

    created = create_user(
        email=request.email,
        password_hash=hash_password(request.password),
        display_name=request.display_name,
        role=request.role,
    )
    return created


@app.get("/api/auth/me")
def me(user: dict = Depends(current_user)) -> dict:
    return user


def chat_history(user_id: str, conversation_id: str) -> list[dict[str, str]]:
    messages = list_conversation_messages(user_id, conversation_id, limit=20)
    return [
        {"role": item["role"], "content": item["content"]}
        for item in messages
        if item["role"] in {"user", "assistant"}
    ][-10:]


def persist_chat_result(
    user_id: str,
    session_id: str,
    user_message: str,
    answer: str,
    approval_request: dict[str, str] | None,
) -> None:
    save_message(user_id, session_id, "user", user_message)
    save_message(
        user_id,
        session_id,
        "assistant",
        answer,
        {"approval_required": approval_request is not None},
    )


def create_agent_approval(
    user_id: str,
    session_id: str,
    request: dict[str, str],
) -> tuple[str, dict[str, str]]:
    record = create_approval_request(
        session_id=session_id,
        source="agent_tool",
        action=request["action"],
        payload=request,
        created_by=user_id,
    )
    response_request = {**request, "approval_id": record["approval_id"]}
    return record["approval_id"], response_request


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, user: dict = Depends(current_user)) -> ChatResponse:
    history = chat_history(user["user_id"], request.session_id)
    result = await process_chat_message(request.message, history)
    approval_id = None
    approval_request = result.approval_request

    if approval_request is not None:
        approval_id, approval_request = create_agent_approval(
            user["user_id"], request.session_id, approval_request
        )

    persist_chat_result(
        user["user_id"],
        request.session_id,
        request.message,
        result.answer,
        approval_request,
    )

    return ChatResponse(
        request_id=str(uuid4()),
        session_id=request.session_id,
        answer=result.answer,
        approval_required=approval_id is not None,
        approval_id=approval_id,
        approval_request=approval_request,
    )


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest, user: dict = Depends(current_user)) -> StreamingResponse:
    async def event_stream():
        history = chat_history(user["user_id"], request.session_id)
        save_message(user["user_id"], request.session_id, "user", request.message)
        chunks: list[str] = []

        try:
            agent = create_support_agent()
            result = Runner.run_streamed(agent, [*history, {"role": "user", "content": request.message}])

            async for event in result.stream_events():
                if isinstance(event, RawResponsesStreamEvent):
                    event_type = getattr(event.data, "type", "")
                    delta = getattr(event.data, "delta", "")
                    if event_type == "response.output_text.delta" and delta:
                        chunks.append(delta)
                        yield sse("token", {"delta": delta})
                elif isinstance(event, RunItemStreamEvent):
                    if event.name in {"tool_called", "tool_output"}:
                        yield sse("tool", {"name": event.name})

            approval_request = find_approval_request(result)
            answer = result.final_output
            approval_id = None

            if approval_request is not None:
                approval_id, approval_request = create_agent_approval(
                    user["user_id"], request.session_id, approval_request
                )
                answer = "该操作需要人工审批，请在审批面板中决定是否执行。"
                yield sse("approval_required", {"approval_id": approval_id, "request": approval_request})

            save_message(
                user["user_id"],
                request.session_id,
                "assistant",
                answer,
                {"approval_required": approval_request is not None, "streamed": True},
            )
            yield sse("done", {"answer": answer, "approval_id": approval_id})
        except Exception as exc:
            yield sse("error", {"message": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/conversations")
def conversations(user: dict = Depends(current_user)) -> list[dict]:
    return list_conversations(user["user_id"])


@app.get("/api/conversations/{conversation_id}/messages")
def conversation_messages(
    conversation_id: str,
    user: dict = Depends(current_user),
) -> list[dict]:
    return list_conversation_messages(user["user_id"], conversation_id)


@app.get("/api/orders")
def orders(
    query: str | None = Query(default=None, max_length=100),
    user: dict = Depends(current_user),
) -> list[dict]:
    return list_orders_from_db(query)


@app.get("/api/orders/{order_id}")
def order_detail(order_id: str, user: dict = Depends(current_user)) -> dict:
    order = get_order_from_db(order_id.strip().upper())
    if order is None:
        raise HTTPException(status_code=404, detail="订单不存在")
    return order


@app.get("/api/tickets")
def tickets(
    status: str | None = Query(default=None, max_length=30),
    user: dict = Depends(current_user),
) -> list[dict]:
    return list_tickets_from_db(status)


@app.get("/api/tickets/{ticket_id}")
def ticket_detail(ticket_id: str, user: dict = Depends(current_user)) -> dict:
    match = re.fullmatch(r"T?(\d+)", ticket_id.strip().upper())
    if match is None:
        raise HTTPException(status_code=400, detail="工单号格式不正确")

    ticket = get_ticket_from_db(int(match.group(1)))
    if ticket is None:
        raise HTTPException(status_code=404, detail="工单不存在")

    ticket["ticket_id"] = f"T{ticket['ticket_id']:04d}"
    return ticket


@app.post("/api/tickets")
def create_ticket(request: TicketCreateRequest, user: dict = Depends(current_user)) -> dict:
    order_id = request.order_id.strip().upper()
    if get_order_from_db(order_id) is None:
        raise HTTPException(status_code=404, detail="订单不存在")

    record = create_approval_request(
        session_id=request.session_id,
        source="ticket_api",
        action="create_ticket",
        payload={
            "order_id": order_id,
            "issue_type": request.issue_type.strip(),
            "description": request.description.strip(),
        },
        created_by=user["user_id"],
    )
    return {"approval_required": True, "approval_id": record["approval_id"], "approval": record}


@app.get("/api/approvals")
def approvals(
    status: str | None = Query(default=None, max_length=20),
    user: dict = Depends(current_user),
) -> list[dict]:
    owner = None if user["role"] in {"admin", "supervisor"} else user["user_id"]
    return list_approval_requests(status, owner)


def execute_approval(record: dict) -> str:
    payload = record["payload"]
    action = record["action"]

    if action == "create_ticket":
        ticket_id = create_ticket_in_db(
            order_id=payload["order_id"],
            issue_type=payload["issue_type"],
            description=payload["description"],
        )
        return f"工单创建成功：T{ticket_id:04d}"

    if action == "update_ticket_status":
        ticket_id = int(payload["ticket_id"].lstrip("T"))
        if not update_ticket_status_in_db(ticket_id, payload["new_status"]):
            raise HTTPException(status_code=409, detail="工单状态更新失败")
        return f"工单 {payload['ticket_id']} 已更新为 {payload['new_status']}"

    if action == "create_shipping_ticket":
        state = ShippingWorkflowState(**payload["state"])
        state = approve_shipping_ticket(state)
        return f"物流工单处理完成：{state.ticket_id or '未创建'}"

    raise HTTPException(status_code=400, detail="不支持的审批动作")


@app.post("/api/approvals/{approval_id}/decision")
def decide_approval(
    approval_id: str,
    request: ApprovalDecisionRequest,
    user: dict = Depends(require_roles("admin", "supervisor")),
) -> dict:
    record = get_approval_request(approval_id)
    if record is None:
        raise HTTPException(status_code=404, detail="审批请求不存在")
    if record["status"] != "pending":
        raise HTTPException(status_code=409, detail="该审批请求已经处理")

    if request.decision == "reject":
        result = "人工拒绝，未执行数据库写入"
        if record["action"] == "create_shipping_ticket":
            state = ShippingWorkflowState(**record["payload"]["state"])
            reject_shipping_ticket(state)
        update_approval_request(approval_id, "rejected", result)
        return {"approval_id": approval_id, "status": "rejected", "result": result}

    result = execute_approval(record)
    update_approval_request(approval_id, "approved", result)
    return {"approval_id": approval_id, "status": "approved", "result": result}


@app.post("/api/shipping-workflows")
def shipping_workflow(
    request: ShippingWorkflowRequest,
    user: dict = Depends(current_user),
) -> dict:
    state = run_shipping_workflow(request.order_id.strip().upper())
    response: dict = {"state": asdict(state), "approval_required": False}

    if state.current_step == "awaiting_approval":
        record = create_approval_request(
            session_id=request.session_id,
            source="shipping_workflow",
            action="create_shipping_ticket",
            payload={"state": asdict(state)},
            created_by=user["user_id"],
        )
        response["approval_required"] = True
        response["approval_id"] = record["approval_id"]

    return response


@app.get("/api/knowledge")
def knowledge(user: dict = Depends(current_user)) -> list[dict]:
    documents = []
    for pattern in ("*.txt", "*.md"):
        for path in sorted(KNOWLEDGE_DIR.glob(pattern)):
            content = path.read_text(encoding="utf-8")
            lines = content.splitlines()
            documents.append(
                {
                    "source": path.name,
                    "title": lines[0] if lines else path.stem,
                    "characters": len(content),
                    "updated_at": path.stat().st_mtime,
                }
            )

    known_sources = {item["source"] for item in documents}
    for item in list_knowledge_documents():
        if item["source"] not in known_sources:
            documents.append(item)
    return documents


@app.post("/api/knowledge/upload")
async def upload_knowledge(
    file: UploadFile = File(...),
    user: dict = Depends(require_roles("admin")),
) -> dict:
    filename = Path(file.filename or "").name
    if Path(filename).suffix.lower() not in {".txt", ".md"}:
        raise HTTPException(status_code=400, detail="当前只支持 .txt 和 .md 文件")

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件不能超过 5 MB")

    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    stored_name = f"uploaded_{uuid4().hex[:8]}_{filename}"
    target = KNOWLEDGE_DIR / stored_name
    target.write_bytes(content)

    try:
        chunks = [chunk for chunk in build_chunks() if chunk["source"] == stored_name]
        await run_in_threadpool(ingest_knowledge_base)
        return save_knowledge_document(
            source=stored_name,
            stored_path=str(target),
            status="indexed",
            chunk_count=len(chunks),
            created_by=user["user_id"],
        )
    except Exception as exc:
        return save_knowledge_document(
            source=stored_name,
            stored_path=str(target),
            status=f"failed: {exc}",
            chunk_count=0,
            created_by=user["user_id"],
        )


@app.get("/api/evals/latest")
def latest_eval(user: dict = Depends(current_user)) -> dict:
    if not EVAL_REPORT_PATH.exists():
        return {"available": False, "release_gate": "UNKNOWN", "report": ""}

    report = EVAL_REPORT_PATH.read_text(encoding="utf-8")
    release_match = re.search(r"Release Gate:\s+\*\*(READY|NOT READY)\*\*", report)
    suite_match = re.search(r"Eval Suites Passed:\s+\*\*(\d+/\d+)\*\*", report)
    return {
        "available": True,
        "release_gate": release_match.group(1) if release_match else "UNKNOWN",
        "suites_passed": suite_match.group(1) if suite_match else "UNKNOWN",
        "report": report,
    }


@app.get("/api/logs")
def logs(
    limit: int = Query(default=30, ge=1, le=200),
    user: dict = Depends(require_roles("admin", "supervisor")),
) -> list[dict]:
    records: list[dict] = []
    for path in sorted(LOG_DIR.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            records.append({"log_type": path.stem, **record})

    records.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
    return records[:limit]
