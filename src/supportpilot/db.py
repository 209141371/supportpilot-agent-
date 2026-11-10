import json
import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "supportpilot.db"


def ensure_orders_schema(cursor: sqlite3.Cursor) -> None:
    """Create the orders table and apply the one-time legacy column migration."""

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            customer_name TEXT,
            product_name TEXT,
            payment_status TEXT,
            shipping_status TEXT,
            estimated_delivery TEXT
        )
        """
    )

    cursor.execute("PRAGMA table_info(orders)")
    columns = {row[1] for row in cursor.fetchall()}

    if "hours_since_payment" not in columns:
        cursor.execute(
            """
            ALTER TABLE orders
            ADD COLUMN hours_since_payment INTEGER NOT NULL DEFAULT 0
            """
        )


def ensure_tickets_schema(cursor: sqlite3.Cursor) -> None:
    """Create the tickets table required by ticket tools and workflows."""

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tickets (
            ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL,
            issue_type TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL
        )
        """
    )


def ensure_approvals_schema(cursor: sqlite3.Cursor) -> None:
    """Create the approval table used by the web API."""

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS approval_requests (
            approval_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            created_by TEXT,
            source TEXT NOT NULL,
            action TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            status TEXT NOT NULL,
            result TEXT,
            created_at TEXT NOT NULL,
            decided_at TEXT
        )
        """
    )
    cursor.execute("PRAGMA table_info(approval_requests)")
    columns = {row[1] for row in cursor.fetchall()}
    if "created_by" not in columns:
        cursor.execute("ALTER TABLE approval_requests ADD COLUMN created_by TEXT")


def ensure_users_schema(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1
        )
        """
    )


def ensure_conversations_schema(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            conversation_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def ensure_messages_schema(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            message_id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata_json TEXT,
            created_at TEXT NOT NULL
        )
        """
    )


def ensure_knowledge_documents_schema(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_documents (
            document_id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            stored_path TEXT NOT NULL,
            status TEXT NOT NULL,
            chunk_count INTEGER NOT NULL DEFAULT 0,
            created_by TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def init_db() -> None:
    """Ensure schemas exist and seed the small deterministic demo dataset."""

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    ensure_orders_schema(cursor)
    ensure_tickets_schema(cursor)
    ensure_approvals_schema(cursor)
    ensure_users_schema(cursor)
    ensure_conversations_schema(cursor)
    ensure_messages_schema(cursor)
    ensure_knowledge_documents_schema(cursor)

    cursor.executemany(
        """
        INSERT OR IGNORE INTO orders (
            order_id,
            customer_name,
            product_name,
            payment_status,
            shipping_status,
            estimated_delivery,
            hours_since_payment
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "A1001",
                "张三",
                "无线蓝牙耳机",
                "已付款",
                "等待仓库发货",
                "预计 2 天内发货",
                72,
            ),
            (
                "A1002",
                "李四",
                "机械键盘",
                "已付款",
                "运输中",
                "预计明天送达",
                30,
            ),
            (
                "A1003",
                "王五",
                "27 英寸显示器",
                "已付款",
                "已签收",
                "已于昨日送达",
                96,
            ),
            (
                "A1004",
                "赵六",
                "智能手环",
                "已付款",
                "等待仓库发货",
                "预计尽快发货",
                60,
            ),
        ],
    )

    conn.commit()
    conn.close()


def get_order_from_db(order_id: str) -> dict | None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

          
    cursor.execute(
        """
        SELECT
            order_id,
            customer_name,
            product_name,
            payment_status,
            shipping_status,
            estimated_delivery,
            hours_since_payment
        FROM orders
        WHERE order_id = ?
        """,
        (order_id,),
    )
       

    row = cursor.fetchone()
    conn.close()

    if row is None:
        return None

    return {
        "order_id": row[0],
        "customer_name": row[1],
        "product_name": row[2],
        "payment_status": row[3],
        "shipping_status": row[4],
        "estimated_delivery": row[5],
        "hours_since_payment": row[6],
    }


def list_orders_from_db(query: str | None = None) -> list[dict]:
    """返回订单列表，支持按订单号、客户或商品搜索。"""

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if query:
        pattern = f"%{query.strip()}%"
        cursor.execute(
            """
            SELECT order_id, customer_name, product_name, payment_status,
                   shipping_status, estimated_delivery, hours_since_payment
            FROM orders
            WHERE order_id LIKE ? OR customer_name LIKE ? OR product_name LIKE ?
            ORDER BY order_id
            """,
            (pattern, pattern, pattern),
        )
    else:
        cursor.execute(
            """
            SELECT order_id, customer_name, product_name, payment_status,
                   shipping_status, estimated_delivery, hours_since_payment
            FROM orders
            ORDER BY order_id
            """
        )

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "order_id": row[0],
            "customer_name": row[1],
            "product_name": row[2],
            "payment_status": row[3],
            "shipping_status": row[4],
            "estimated_delivery": row[5],
            "hours_since_payment": row[6],
        }
        for row in rows
    ]
def create_ticket_in_db(
    order_id: str,
    issue_type: str,
    description: str,
) -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO tickets (
            order_id,
            issue_type,
            description,
            status
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            order_id,
            issue_type,
            description,
            "已创建",
        ),
    )

    ticket_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return ticket_id
def get_ticket_from_db(ticket_id: int) -> dict | None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            ticket_id,
            order_id,
            issue_type,
            description,
            status
        FROM tickets
        WHERE ticket_id = ?
        """,
        (ticket_id,),
    )

    row = cursor.fetchone()
    conn.close()

    if row is None:
        return None

    return {
        "ticket_id": row[0],
        "order_id": row[1],
        "issue_type": row[2],
        "description": row[3],
        "status": row[4],
    }


def list_tickets_from_db(status: str | None = None) -> list[dict]:
    """返回工单列表，可按状态筛选。"""

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if status:
        cursor.execute(
            """
            SELECT ticket_id, order_id, issue_type, description, status
            FROM tickets
            WHERE status = ?
            ORDER BY ticket_id DESC
            """,
            (status,),
        )
    else:
        cursor.execute(
            """
            SELECT ticket_id, order_id, issue_type, description, status
            FROM tickets
            ORDER BY ticket_id DESC
            """
        )

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "ticket_id": f"T{row[0]:04d}",
            "order_id": row[1],
            "issue_type": row[2],
            "description": row[3],
            "status": row[4],
        }
        for row in rows
    ]
def update_ticket_status_in_db(
    ticket_id: int,
    new_status: str,
) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE tickets
        SET status = ?
        WHERE ticket_id = ?
        """,
        (
            new_status,
            ticket_id,
        ),
    )

    updated = cursor.rowcount > 0

    conn.commit()
    conn.close()

    return updated
def find_open_ticket_by_order_and_type(
    order_id: str,
    issue_type: str,
) -> dict | None:
    """查找同一订单下尚未解决的同类型工单。"""

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            ticket_id,
            order_id,
            issue_type,
            description,
            status
        FROM tickets
        WHERE order_id = ?
          AND issue_type = ?
          AND status != '已解决'
        ORDER BY ticket_id DESC
        LIMIT 1
        """,
        (
            order_id,
            issue_type,
        ),
    )

    row = cursor.fetchone()

    conn.close()

    if row is None:
        return None

    return {
        "ticket_id": row[0],
        "order_id": row[1],
        "issue_type": row[2],
        "description": row[3],
        "status": row[4],
    }


def create_approval_request(
    session_id: str,
    source: str,
    action: str,
    payload: dict,
    created_by: str | None = None,
) -> dict:
    """持久化一条待审批写操作。"""

    approval_id = f"APR-{uuid4().hex[:10].upper()}"
    created_at = datetime.now().isoformat()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO approval_requests (
            approval_id, session_id, created_by, source, action, payload_json,
            status, result, created_at, decided_at
        )
        VALUES (?, ?, ?, ?, ?, ?, 'pending', NULL, ?, NULL)
        """,
        (
            approval_id,
            session_id,
            created_by,
            source,
            action,
            json.dumps(payload, ensure_ascii=False),
            created_at,
        ),
    )
    conn.commit()
    conn.close()

    return {
        "approval_id": approval_id,
        "session_id": session_id,
        "created_by": created_by,
        "source": source,
        "action": action,
        "payload": payload,
        "status": "pending",
        "result": None,
        "created_at": created_at,
        "decided_at": None,
    }


def get_approval_request(approval_id: str) -> dict | None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT approval_id, session_id, created_by, source, action, payload_json,
               status, result, created_at, decided_at
        FROM approval_requests
        WHERE approval_id = ?
        """,
        (approval_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if row is None:
        return None

    return {
        "approval_id": row[0],
        "session_id": row[1],
        "created_by": row[2],
        "source": row[3],
        "action": row[4],
        "payload": json.loads(row[5]),
        "status": row[6],
        "result": row[7],
        "created_at": row[8],
        "decided_at": row[9],
    }


def list_approval_requests(
    status: str | None = None,
    created_by: str | None = None,
) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if status and created_by:
        cursor.execute(
            """
            SELECT approval_id, session_id, created_by, source, action, payload_json,
                   status, result, created_at, decided_at
            FROM approval_requests
            WHERE status = ? AND created_by = ?
            ORDER BY created_at DESC
            """,
            (status, created_by),
        )
    elif status:
        cursor.execute(
            """
            SELECT approval_id, session_id, created_by, source, action, payload_json,
                   status, result, created_at, decided_at
            FROM approval_requests
            WHERE status = ?
            ORDER BY created_at DESC
            """,
            (status,),
        )
    elif created_by:
        cursor.execute(
            """
            SELECT approval_id, session_id, created_by, source, action, payload_json,
                   status, result, created_at, decided_at
            FROM approval_requests
            WHERE created_by = ?
            ORDER BY created_at DESC
            """,
            (created_by,),
        )
    else:
        cursor.execute(
            """
            SELECT approval_id, session_id, created_by, source, action, payload_json,
                   status, result, created_at, decided_at
            FROM approval_requests
            ORDER BY created_at DESC
            """
        )

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "approval_id": row[0],
            "session_id": row[1],
            "created_by": row[2],
            "source": row[3],
            "action": row[4],
            "payload": json.loads(row[5]),
            "status": row[6],
            "result": row[7],
            "created_at": row[8],
            "decided_at": row[9],
        }
        for row in rows
    ]


def update_approval_request(
    approval_id: str,
    status: str,
    result: str,
) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE approval_requests
        SET status = ?, result = ?, decided_at = ?
        WHERE approval_id = ? AND status = 'pending'
        """,
        (status, result, datetime.now().isoformat(), approval_id),
    )
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated


def count_users() -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    conn.close()
    return count


def create_user(
    email: str,
    password_hash: str,
    display_name: str,
    role: str,
) -> dict:
    user_id = f"USR-{uuid4().hex[:10].upper()}"
    created_at = datetime.now().isoformat()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO users (
            user_id, email, password_hash, display_name, role, created_at, is_active
        )
        VALUES (?, ?, ?, ?, ?, ?, 1)
        """,
        (user_id, email.lower(), password_hash, display_name, role, created_at),
    )
    conn.commit()
    conn.close()

    return {
        "user_id": user_id,
        "email": email.lower(),
        "display_name": display_name,
        "role": role,
        "created_at": created_at,
    }


def get_user_by_email(email: str) -> dict | None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT user_id, email, password_hash, display_name, role, created_at, is_active
        FROM users
        WHERE email = ?
        """,
        (email.lower(),),
    )
    row = cursor.fetchone()
    conn.close()

    if row is None:
        return None

    return {
        "user_id": row[0],
        "email": row[1],
        "password_hash": row[2],
        "display_name": row[3],
        "role": row[4],
        "created_at": row[5],
        "is_active": bool(row[6]),
    }


def get_user_by_id(user_id: str) -> dict | None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT user_id, email, display_name, role, created_at, is_active
        FROM users
        WHERE user_id = ?
        """,
        (user_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if row is None:
        return None

    return {
        "user_id": row[0],
        "email": row[1],
        "display_name": row[2],
        "role": row[3],
        "created_at": row[4],
        "is_active": bool(row[5]),
    }


def get_or_create_conversation(
    user_id: str,
    conversation_id: str,
    title: str,
) -> dict:
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT conversation_id, user_id, title, created_at, updated_at
        FROM conversations
        WHERE conversation_id = ? AND user_id = ?
        """,
        (conversation_id, user_id),
    )
    row = cursor.fetchone()

    if row is None:
        cursor.execute(
            """
            INSERT INTO conversations (
                conversation_id, user_id, title, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (conversation_id, user_id, title[:80] or "新会话", now, now),
        )
        result = {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "title": title[:80] or "新会话",
            "created_at": now,
            "updated_at": now,
        }
    else:
        result = {
            "conversation_id": row[0],
            "user_id": row[1],
            "title": row[2],
            "created_at": row[3],
            "updated_at": row[4],
        }

    conn.commit()
    conn.close()
    return result


def list_conversations(user_id: str) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT conversation_id, user_id, title, created_at, updated_at
        FROM conversations
        WHERE user_id = ?
        ORDER BY updated_at DESC
        """,
        (user_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "conversation_id": row[0],
            "user_id": row[1],
            "title": row[2],
            "created_at": row[3],
            "updated_at": row[4],
        }
        for row in rows
    ]


def list_conversation_messages(
    user_id: str,
    conversation_id: str,
    limit: int = 100,
) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT m.message_id, m.conversation_id, m.role, m.content,
               m.metadata_json, m.created_at
        FROM messages AS m
        INNER JOIN conversations AS c
            ON c.conversation_id = m.conversation_id
        WHERE c.user_id = ? AND m.conversation_id = ?
        ORDER BY m.created_at ASC
        LIMIT ?
        """,
        (user_id, conversation_id, limit),
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "message_id": row[0],
            "conversation_id": row[1],
            "role": row[2],
            "content": row[3],
            "metadata": json.loads(row[4]) if row[4] else {},
            "created_at": row[5],
        }
        for row in rows
    ]


def save_message(
    user_id: str,
    conversation_id: str,
    role: str,
    content: str,
    metadata: dict | None = None,
) -> dict:
    conversation = get_or_create_conversation(user_id, conversation_id, content)
    message_id = f"MSG-{uuid4().hex[:10].upper()}"
    created_at = datetime.now().isoformat()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO messages (
            message_id, conversation_id, role, content, metadata_json, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            message_id,
            conversation_id,
            role,
            content,
            json.dumps(metadata or {}, ensure_ascii=False),
            created_at,
        ),
    )
    cursor.execute(
        "UPDATE conversations SET updated_at = ? WHERE conversation_id = ? AND user_id = ?",
        (created_at, conversation_id, user_id),
    )
    conn.commit()
    conn.close()

    return {
        "message_id": message_id,
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
        "metadata": metadata or {},
        "created_at": created_at,
        "conversation": conversation,
    }


def save_knowledge_document(
    source: str,
    stored_path: str,
    status: str,
    chunk_count: int,
    created_by: str | None,
) -> dict:
    document_id = f"DOC-{uuid4().hex[:10].upper()}"
    now = datetime.now().isoformat()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO knowledge_documents (
            document_id, source, stored_path, status, chunk_count,
            created_by, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (document_id, source, stored_path, status, chunk_count, created_by, now, now),
    )
    conn.commit()
    conn.close()

    return {
        "document_id": document_id,
        "source": source,
        "stored_path": stored_path,
        "status": status,
        "chunk_count": chunk_count,
        "created_by": created_by,
        "created_at": now,
        "updated_at": now,
    }


def list_knowledge_documents() -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT document_id, source, stored_path, status, chunk_count,
               created_by, created_at, updated_at
        FROM knowledge_documents
        ORDER BY updated_at DESC
        """
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "document_id": row[0],
            "source": row[1],
            "stored_path": row[2],
            "status": row[3],
            "chunk_count": row[4],
            "created_by": row[5],
            "created_at": row[6],
            "updated_at": row[7],
        }
        for row in rows
    ]
