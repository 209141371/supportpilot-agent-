import { FormEvent, useEffect, useMemo, useRef, useState } from 'react'

type Order = {
  order_id: string
  customer_name: string
  product_name: string
  payment_status: string
  shipping_status: string
  estimated_delivery: string
  hours_since_payment: number
}

type Ticket = {
  ticket_id: string
  order_id: string
  issue_type: string
  description: string
  status: string
}

type Message = {
  id: number
  role: 'user' | 'assistant'
  content: string
  time: string
}

type ApprovalRecord = {
  approval_id: string
  action: string
  payload: Record<string, any>
  status: 'pending' | 'approved' | 'rejected'
  result?: string | null
  created_at: string
}

type PendingApproval = {
  approvalId: string
  action: string
  target: string
  reason: string
  status: ApprovalRecord['status']
}

type KnowledgeDocument = {
  source: string
  title: string
  characters: number
  updated_at: number
  status?: string
  chunk_count?: number
}

type EvalSummary = {
  available: boolean
  release_gate: string
  suites_passed?: string
  report?: string
}

type ChatResponse = {
  answer: string
  approval_required: boolean
  approval_id?: string | null
  approval_request?: Record<string, string> | null
}

type ShippingResponse = {
  state: Record<string, any>
  approval_required: boolean
  approval_id?: string
}

type AuthUser = {
  user_id: string
  email: string
  display_name: string
  role: string
}

type Conversation = {
  conversation_id: string
  title: string
  updated_at: string
}

const navItems = ['工作台', '工单中心', '订单中心', '知识库', '评测中心']

async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('supportpilot_access_token')
  const response = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers as Record<string, string> | undefined),
    },
  })

  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { detail?: string }
    throw new Error(body.detail || `请求失败：${response.status}`)
  }

  return response.json() as Promise<T>
}

async function streamFetch(
  path: string,
  body: unknown,
  onEvent: (event: string, data: Record<string, any>) => void,
) {
  const token = localStorage.getItem('supportpilot_access_token')
  const response = await fetch(path, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  })

  if (!response.ok || !response.body) {
    const result = await response.json().catch(() => ({})) as { detail?: string }
    throw new Error(result.detail || `流式请求失败：${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() || ''

    for (const block of blocks) {
      const eventLine = block.split('\n').find((line) => line.startsWith('event:'))
      const dataLine = block.split('\n').find((line) => line.startsWith('data:'))
      if (!eventLine || !dataLine) continue
      onEvent(eventLine.replace('event:', '').trim(), JSON.parse(dataLine.replace('data:', '').trim()))
    }

    if (done) break
  }
}

function nowText() {
  return new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit' }).format(new Date())
}

function approvalFromRequest(
  approvalId: string,
  request: Record<string, any>,
): PendingApproval {
  if (request.action === 'create_ticket') {
    return {
      approvalId,
      action: '创建售后工单',
      target: `订单 ${request.order_id ?? '未知'}`,
      reason: `问题类型：${request.issue_type ?? '未提供'}。${request.description ?? ''}`,
      status: 'pending',
    }
  }

  if (request.action === 'create_shipping_ticket') {
    const state = request.state ?? request
    return {
      approvalId,
      action: '创建物流异常工单',
      target: `订单 ${state.order_id ?? '未知'}`,
      reason: state.approval_reason || '物流工作流判断需要创建工单。',
      status: 'pending',
    }
  }

  return {
    approvalId,
    action: '修改工单状态',
    target: `工单 ${request.ticket_id ?? '未知'}`,
    reason: `状态变更：${request.old_status ?? '未知'} → ${request.new_status ?? '未知'}`,
    status: 'pending',
  }
}

function approvalFromRecord(record: ApprovalRecord): PendingApproval {
  return approvalFromRequest(record.approval_id, { action: record.action, ...record.payload })
}

function App() {
  const [auth, setAuth] = useState<{ token: string; user: AuthUser } | null>(() => {
    const token = localStorage.getItem('supportpilot_access_token')
    const user = localStorage.getItem('supportpilot_user')
    if (!token || !user) return null
    try {
      return { token, user: JSON.parse(user) as AuthUser }
    } catch {
      return null
    }
  })
  const [activeNav, setActiveNav] = useState('工作台')
  const [apiStatus, setApiStatus] = useState<'connected' | 'offline'>('offline')
  const [error, setError] = useState('')
  const [sessionId, setSessionId] = useState(() => {
    const stored = localStorage.getItem('supportpilot_conversation_id')
    if (stored) return stored
    const created = `web-${Date.now()}`
    localStorage.setItem('supportpilot_conversation_id', created)
    return created
  })
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 1,
      role: 'assistant',
      content: '你好，我是 SupportPilot。可以帮你查询订单、处理工单或检索企业政策。',
      time: nowText(),
    },
  ])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [orders, setOrders] = useState<Order[]>([])
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [approvals, setApprovals] = useState<ApprovalRecord[]>([])
  const [knowledge, setKnowledge] = useState<KnowledgeDocument[]>([])
  const [evalSummary, setEvalSummary] = useState<EvalSummary | null>(null)
  const [logs, setLogs] = useState<Record<string, any>[]>([])
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [selectedOrder, setSelectedOrder] = useState<Order | null>(null)
  const [pendingApproval, setPendingApproval] = useState<PendingApproval | null>(null)
  const [orderQuery, setOrderQuery] = useState('')
  const [ticketForm, setTicketForm] = useState({ order_id: 'A1004', issue_type: '售后问题', description: '' })

  const uploadInputRef = useRef<HTMLInputElement>(null)

  const pendingCount = useMemo(
    () => approvals.filter((item) => item.status === 'pending').length,
    [approvals],
  )

  async function refreshData() {
    const results = await Promise.allSettled([
      apiFetch<Order[]>('/api/orders'),
      apiFetch<Ticket[]>('/api/tickets'),
      apiFetch<ApprovalRecord[]>('/api/approvals'),
      apiFetch<KnowledgeDocument[]>('/api/knowledge'),
      apiFetch<EvalSummary>('/api/evals/latest'),
      apiFetch<Record<string, any>[]>('/api/logs?limit=20'),
      apiFetch<Conversation[]>('/api/conversations'),
    ])

    const [orderResult, ticketResult, approvalResult, knowledgeResult, evalResult, logResult, conversationResult] = results
    let loaded = false

    if (orderResult.status === 'fulfilled') {
      setOrders(orderResult.value)
      setSelectedOrder((current) => current || orderResult.value[0] || null)
      loaded = true
    }
    if (ticketResult.status === 'fulfilled') {
      setTickets(ticketResult.value)
      loaded = true
    }
    if (approvalResult.status === 'fulfilled') {
      setApprovals(approvalResult.value)
      const firstPending = approvalResult.value.find((item) => item.status === 'pending')
      if (firstPending) setPendingApproval(approvalFromRecord(firstPending))
      loaded = true
    }
    if (knowledgeResult.status === 'fulfilled') {
      setKnowledge(knowledgeResult.value)
      loaded = true
    }
    if (evalResult.status === 'fulfilled') {
      setEvalSummary(evalResult.value)
      loaded = true
    }
    if (logResult.status === 'fulfilled') {
      setLogs(logResult.value)
      loaded = true
    }
    if (conversationResult.status === 'fulfilled') {
      setConversations(conversationResult.value)
      loaded = true
    }

    setApiStatus(loaded ? 'connected' : 'offline')
    if (!loaded) setError('无法连接 FastAPI，请确认后端运行在 127.0.0.1:8000。')
  }

  async function loadConversation(conversationId = sessionId) {
    try {
      const storedMessages = await apiFetch<{ role: 'user' | 'assistant'; content: string; created_at: string }[]>(
        `/api/conversations/${conversationId}/messages`,
      )
      if (storedMessages.length > 0) {
        setMessages(storedMessages.map((item, index) => ({
          id: index + 1,
          role: item.role,
          content: item.content,
          time: new Date(item.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
        })))
      }
    } catch {
      // 首次进入时还没有会话记录，保留欢迎消息即可。
    }
  }

  useEffect(() => {
    if (!auth) return
    void apiFetch<AuthUser>('/api/auth/me').catch(() => {
      localStorage.removeItem('supportpilot_access_token')
      localStorage.removeItem('supportpilot_user')
      setAuth(null)
    })
    void refreshData()
    void loadConversation()
  }, [auth])

  if (!auth) {
    return <AuthPage onAuthenticated={(value) => setAuth(value)} />
  }

  function logout() {
    localStorage.removeItem('supportpilot_access_token')
    localStorage.removeItem('supportpilot_user')
    setAuth(null)
  }

  function startNewConversation() {
    const created = `web-${Date.now()}`
    localStorage.setItem('supportpilot_conversation_id', created)
    setSessionId(created)
    setMessages([{
      id: Date.now(),
      role: 'assistant',
      content: '你好，我是 SupportPilot。可以帮你查询订单、处理工单或检索企业政策。',
      time: nowText(),
    }])
    setActiveNav('工作台')
  }

  function selectConversation(conversationId: string) {
    localStorage.setItem('supportpilot_conversation_id', conversationId)
    setSessionId(conversationId)
    setMessages([])
    setActiveNav('工作台')
    void loadConversation(conversationId)
  }

  async function sendMessage(event?: FormEvent) {
    event?.preventDefault()
    const content = input.trim()
    if (!content || sending) return

    setMessages((current) => [
      ...current,
      { id: Date.now(), role: 'user', content, time: nowText() },
    ])
    setInput('')
    setSending(true)
    setError('')

    try {
      const assistantId = Date.now() + 1
      setMessages((current) => [
        ...current,
        { id: assistantId, role: 'assistant', content: '', time: nowText() },
      ])
      let streamedAnswer = ''
      let streamApproval: { approval_id: string; request: Record<string, string> } | null = null

      await streamFetch(
        '/api/chat/stream',
        { session_id: sessionId, message: content },
        (event, data) => {
          if (event === 'token') {
            streamedAnswer += String(data.delta || '')
            setMessages((current) => current.map((item) => item.id === assistantId ? { ...item, content: streamedAnswer } : item))
          }
          if (event === 'approval_required') {
            streamApproval = data as { approval_id: string; request: Record<string, string> }
          }
          if (event === 'error') {
            throw new Error(String(data.message || 'Agent 流式处理失败'))
          }
          if (event === 'done' && data.answer) {
            streamedAnswer = String(data.answer)
            setMessages((current) => current.map((item) => item.id === assistantId ? { ...item, content: streamedAnswer } : item))
          }
        },
      )
      setApiStatus('connected')
      const approvalEvent = streamApproval as { approval_id: string; request: Record<string, string> } | null
      if (approvalEvent) {
        setPendingApproval(approvalFromRequest(approvalEvent.approval_id, approvalEvent.request))
        void refreshData()
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '请求失败')
      setMessages((current) => [
        ...current,
        {
          id: Date.now(),
          role: 'assistant',
          content: '后端请求失败，请检查 FastAPI 服务和 API Key 配置。',
          time: nowText(),
        },
      ])
      setApiStatus('offline')
    } finally {
      setSending(false)
    }
  }

  async function decideApproval(decision: 'approve' | 'reject') {
    if (!pendingApproval || pendingApproval.status !== 'pending') return

    try {
      const result = await apiFetch<{ status: ApprovalRecord['status']; result: string }>(
        `/api/approvals/${pendingApproval.approvalId}/decision`,
        { method: 'POST', body: JSON.stringify({ decision }) },
      )
      setPendingApproval((current) => current && { ...current, status: result.status })
      setMessages((current) => [
        ...current,
        { id: Date.now(), role: 'assistant', content: result.result, time: nowText() },
      ])
      await refreshData()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '审批失败')
    }
  }

  async function runShippingWorkflow(orderId: string) {
    try {
      const data = await apiFetch<ShippingResponse>('/api/shipping-workflows', {
        method: 'POST',
        body: JSON.stringify({ session_id: sessionId, order_id: orderId }),
      })
      const state = data.state
      setMessages((current) => [
        ...current,
        {
          id: Date.now(),
          role: 'assistant',
          content: data.approval_required
            ? `订单 ${orderId} 需要审批：${state.approval_reason || '需要创建物流工单。'}`
            : `物流工作流完成：${state.current_step}。工单：${state.ticket_id || '无'}`,
          time: nowText(),
        },
      ])
      if (data.approval_required && data.approval_id) {
        setPendingApproval(approvalFromRequest(data.approval_id, { action: 'create_shipping_ticket', state }))
        await refreshData()
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '工作流执行失败')
    }
  }

  async function searchOrders(event?: FormEvent) {
    event?.preventDefault()
    try {
      const query = orderQuery.trim()
      const data = await apiFetch<Order[]>(`/api/orders${query ? `?query=${encodeURIComponent(query)}` : ''}`)
      setOrders(data)
      setSelectedOrder(data[0] || null)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '订单查询失败')
    }
  }

  async function createTicket(event: FormEvent) {
    event.preventDefault()
    try {
      const result = await apiFetch<{ approval_id: string; approval: ApprovalRecord }>('/api/tickets', {
        method: 'POST',
        body: JSON.stringify({ session_id: sessionId, ...ticketForm }),
      })
      setPendingApproval(approvalFromRecord(result.approval))
      setTicketForm((current) => ({ ...current, description: '' }))
      await refreshData()
      setActiveNav('工作台')
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '创建工单失败')
    }
  }

  async function uploadKnowledge(event: FormEvent) {
    event.preventDefault()
    const file = uploadInputRef.current?.files?.[0]
    if (!file) return

    try {
      const token = localStorage.getItem('supportpilot_access_token')
      const formData = new FormData()
      formData.append('file', file)
      const response = await fetch('/api/knowledge/upload', {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: formData,
      })
      if (!response.ok) {
        const result = await response.json().catch(() => ({})) as { detail?: string }
        throw new Error(result.detail || `上传失败：${response.status}`)
      }
      if (uploadInputRef.current) uploadInputRef.current.value = ''
      await refreshData()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '知识库上传失败')
    }
  }

  function renderWorkbench() {
    return (
      <>
        <section className="metrics-grid" aria-label="今日概览">
          <div className="metric-card"><span>订单总数</span><strong>{orders.length}</strong><small>SQLite 业务数据</small></div>
          <div className="metric-card"><span>未解决工单</span><strong>{tickets.filter((item) => item.status !== '已解决').length}</strong><small className="warning-text">持续跟进中</small></div>
          <div className="metric-card"><span>待审批动作</span><strong>{pendingCount}</strong><small className="warning-text">需要人工确认</small></div>
          <div className="metric-card accent-card"><span>Eval Release Gate</span><strong>{evalSummary?.release_gate || 'UNKNOWN'}</strong><small>{evalSummary?.suites_passed || '等待评测报告'}</small></div>
        </section>

        <section className="workspace-grid">
          <div className="panel chat-panel">
            <div className="panel-header">
              <div><span className="panel-kicker">LIVE CONVERSATION</span><h2>客户对话</h2></div>
              <span className="session-label"><span className="status-dot" />{apiStatus === 'connected' ? 'API 已连接' : 'API 离线'}</span>
            </div>
            <div className="message-list">
              {messages.map((message) => (
                <div className={`message-row ${message.role}`} key={message.id}>
                  {message.role === 'assistant' && <div className="assistant-avatar">S</div>}
                  <div className="message-content">
                    <div className="message-meta"><strong>{message.role === 'assistant' ? 'SupportPilot' : '客户'}</strong><time>{message.time}</time></div>
                    <div className="message-bubble">{message.content}</div>
                  </div>
                </div>
              ))}
              {sending && <div className="typing-indicator">SupportPilot 正在处理…</div>}
            </div>
            <div className="quick-actions"><span>快捷问题</span><button onClick={() => setInput('查询订单 A1001')}>查询订单 A1001</button><button onClick={() => setInput('查询退款政策')}>查询退款政策</button><button onClick={() => setInput('物流异常 A1004')}>物流异常 A1004</button></div>
            <form className="composer" onSubmit={sendMessage}>
              <textarea value={input} onChange={(event) => setInput(event.target.value)} placeholder="输入客户问题，例如：查询订单 A1001" rows={2} />
              <div className="composer-footer"><span>消息会发送到 FastAPI Agent</span><button className="send-button" type="submit" disabled={sending}>发送 <span>↗</span></button></div>
            </form>
          </div>

          <div className="right-column">
            <ApprovalCard approval={pendingApproval} onDecision={decideApproval} />
            <div className="panel order-panel">
              <div className="panel-header compact"><div><span className="panel-kicker">BUSINESS DATA</span><h2>当前订单</h2></div><button className="text-button" onClick={() => setActiveNav('订单中心')}>查看全部</button></div>
              {selectedOrder ? <OrderSummary order={selectedOrder} onWorkflow={runShippingWorkflow} /> : <EmptyState text="暂无订单数据" />}
            </div>
            <div className="panel detail-panel">
              <div className="panel-header compact"><div><span className="panel-kicker">KNOWLEDGE BASE</span><h2>知识库状态</h2></div><button className="text-button" onClick={() => setActiveNav('知识库')}>管理</button></div>
              <div className="compact-list">{knowledge.slice(0, 3).map((item) => <div className="compact-list-row" key={item.source}><span>▤</span><strong>{item.source}</strong><small>{item.characters} 字</small></div>)}</div>
            </div>
          </div>
        </section>
      </>
    )
  }

  function renderTickets() {
    return <div className="page-view two-column-view"><section className="panel data-panel"><PageTitle kicker="TICKET CENTER" title="工单中心" description="查看工单状态，并追踪需要人工处理的售后事项。" /><div className="filter-row"><button className="filter-button active">全部 {tickets.length}</button><button className="filter-button">处理中</button><button className="filter-button">已解决</button></div><div className="table-wrap"><table><thead><tr><th>工单</th><th>订单</th><th>问题类型</th><th>描述</th><th>状态</th></tr></thead><tbody>{tickets.map((ticket) => <tr key={ticket.ticket_id}><td><strong>{ticket.ticket_id}</strong></td><td>{ticket.order_id}</td><td>{ticket.issue_type}</td><td className="description-cell">{ticket.description}</td><td><StatusTag value={ticket.status} /></td></tr>)}</tbody></table></div></section><section className="panel form-panel"><PageTitle kicker="NEW TICKET" title="创建工单" description="写操作会先生成审批请求，不会直接修改数据库。" /><form onSubmit={createTicket} className="business-form"><label>订单号<input value={ticketForm.order_id} onChange={(event) => setTicketForm({ ...ticketForm, order_id: event.target.value })} /></label><label>问题类型<input value={ticketForm.issue_type} onChange={(event) => setTicketForm({ ...ticketForm, issue_type: event.target.value })} /></label><label>问题描述<textarea required value={ticketForm.description} onChange={(event) => setTicketForm({ ...ticketForm, description: event.target.value })} placeholder="描述客户遇到的问题" rows={5} /></label><button className="primary-button" type="submit">提交审批</button></form><ApprovalCard approval={pendingApproval} onDecision={decideApproval} /></section></div>
  }

  function renderOrders() {
    return <div className="page-view two-column-view"><section className="panel data-panel"><PageTitle kicker="ORDER CENTER" title="订单中心" description="查询订单业务数据，物流异常可以直接进入确定性工作流。" /><form className="search-form" onSubmit={searchOrders}><input value={orderQuery} onChange={(event) => setOrderQuery(event.target.value)} placeholder="搜索订单号、客户或商品" /><button className="primary-button" type="submit">搜索</button></form><div className="order-list">{orders.map((order) => <button className={selectedOrder?.order_id === order.order_id ? 'order-list-item selected' : 'order-list-item'} key={order.order_id} onClick={() => setSelectedOrder(order)}><span className="order-list-id">{order.order_id}</span><span><strong>{order.product_name}</strong><small>{order.customer_name} · {order.shipping_status}</small></span><StatusTag value={order.shipping_status} /></button>)}</div></section><section className="panel detail-panel order-detail-card">{selectedOrder ? <><PageTitle kicker="ORDER DETAIL" title={selectedOrder.order_id} description={`${selectedOrder.customer_name} · ${selectedOrder.product_name}`} /><OrderSummary order={selectedOrder} onWorkflow={runShippingWorkflow} /></> : <EmptyState text="选择一个订单查看详情" />}</section></div>
  }

  function renderKnowledge() {
    return <div className="page-view"><section className="panel data-panel"><PageTitle kicker="KNOWLEDGE BASE" title="企业知识库" description="当前政策文件由 RAG 检索工具使用，回答会引用真实来源。" />{auth?.user.role === 'admin' && <form className="upload-form" onSubmit={uploadKnowledge}><input ref={uploadInputRef} type="file" accept=".txt,.md" /><button className="primary-button" type="submit">上传并重新索引</button></form>}<div className="knowledge-grid">{knowledge.map((item) => <div className="knowledge-card" key={item.source}><div className="knowledge-icon">◇</div><strong>{item.title || item.source}</strong><span>{item.source}</span><small>{item.characters ? `${item.characters} 字` : `${item.chunk_count || 0} chunks`} · {item.status || '已纳入索引'}</small></div>)}</div></section></div>
  }

  function renderEvals() {
    return <div className="page-view"><section className="panel data-panel"><PageTitle kicker="QUALITY GATE" title="评测中心" description="查看最近一次回归评测、Release Gate 和运行日志。" /><div className="eval-summary"><div className="eval-gate"><span>Release Gate</span><strong>{evalSummary?.release_gate || 'UNKNOWN'}</strong><small>{evalSummary?.suites_passed || '暂无报告'}</small></div><div className="eval-copy">{evalSummary?.available ? '当前报告来自项目内的 controlled regression / smoke-test 数据集。' : '尚未生成 eval_report.md，请运行 python evals/run_all_evals.py。'}</div></div><h3 className="subheading">评测报告</h3><pre className="report-view">{evalSummary?.report || '暂无评测报告'}</pre><h3 className="subheading">最近运行日志</h3><div className="log-list">{logs.slice(0, 10).map((item, index) => <div className="log-row" key={`${item.timestamp}-${index}`}><span>{item.log_type}</span><strong>{item.timestamp || '未知时间'}</strong><small>{item.message || item.current_step || item.source || '记录已保存'}</small></div>)}</div></section></div>
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><div className="brand-mark">S</div><div><strong>SupportPilot</strong><span>客服工作台</span></div></div>
        <nav className="main-nav" aria-label="主导航">{navItems.map((item) => <button className={activeNav === item ? 'nav-item active' : 'nav-item'} key={item} onClick={() => setActiveNav(item)}><span className="nav-icon">{item === '工作台' ? '⌂' : item === '工单中心' ? '▣' : item === '订单中心' ? '◫' : item === '知识库' ? '◇' : '◌'}</span>{item}</button>)}</nav>
        <div className="sidebar-section conversation-section"><div className="section-heading"><span>历史会话</span><button className="text-button" onClick={startNewConversation}>新建</button></div>{conversations.slice(0, 5).map((conversation) => <button className={conversation.conversation_id === sessionId ? 'conversation-row active' : 'conversation-row'} key={conversation.conversation_id} onClick={() => selectConversation(conversation.conversation_id)}><span className="conversation-icon">▱</span><span><strong>{conversation.title || '新会话'}</strong><small>{new Date(conversation.updated_at).toLocaleDateString('zh-CN')}</small></span></button>)}{conversations.length === 0 && <div className="sidebar-empty">发送第一条消息后会保存会话</div>}</div>
        <div className="sidebar-section approval-section"><div className="section-heading"><span>待审批</span><button className="text-button" onClick={() => setActiveNav('工作台')}>{pendingCount} 条</button></div>{approvals.filter((item) => item.status === 'pending').slice(0, 3).map((item) => <button className="ticket-row selected" key={item.approval_id} onClick={() => setPendingApproval(approvalFromRecord(item))}><span className="ticket-status waiting" /><span><strong>{item.approval_id}</strong><small>{item.action}</small></span><time>待处理</time></button>)}{pendingCount === 0 && <div className="sidebar-empty">当前没有待审批动作</div>}</div>
        <div className="sidebar-footer"><div className="agent-avatar">陈</div><div><strong>陈客服</strong><span>在线 · 客服专员</span></div><button className="more-button">•••</button></div>
      </aside>
      <main className="main-content">
        <header className="topbar"><div><p className="eyebrow">CUSTOMER SUPPORT / 01</p><h1>{activeNav}</h1></div><div className="topbar-actions"><span className="demo-badge"><span className={`status-dot ${apiStatus}`} />{apiStatus === 'connected' ? 'API 已连接' : 'API 离线'}</span><span className="user-chip">{auth.user.display_name} · {auth.user.role}</span><button className="icon-button" onClick={() => void refreshData()} aria-label="刷新">↻</button><button className="help-button" onClick={logout}>退出登录</button></div></header>
        {error && <div className="error-banner">{error}<button onClick={() => setError('')}>关闭</button></div>}
        {activeNav === '工作台' && renderWorkbench()}
        {activeNav === '工单中心' && renderTickets()}
        {activeNav === '订单中心' && renderOrders()}
        {activeNav === '知识库' && renderKnowledge()}
        {activeNav === '评测中心' && renderEvals()}
        <footer className="page-footer">SupportPilot · 企业客服 Agent <span>FastAPI + React 工作台</span></footer>
      </main>
    </div>
  )
}

function PageTitle({ kicker, title, description }: { kicker: string; title: string; description: string }) {
  return <div className="page-title"><span className="panel-kicker">{kicker}</span><h2>{title}</h2><p>{description}</p></div>
}

function AuthPage({ onAuthenticated }: { onAuthenticated: (value: { token: string; user: AuthUser }) => void }) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setLoading(true)
    setError('')

    try {
      const endpoint = mode === 'login' ? '/api/auth/login' : '/api/auth/register'
      const body = mode === 'login' ? { email, password } : { email, password, display_name: displayName }
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await response.json() as { detail?: string; access_token?: string; user?: AuthUser }
      if (!response.ok || !data.access_token || !data.user) throw new Error(data.detail || '认证失败')

      localStorage.setItem('supportpilot_access_token', data.access_token)
      localStorage.setItem('supportpilot_user', JSON.stringify(data.user))
      onAuthenticated({ token: data.access_token, user: data.user })
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '认证失败')
    } finally {
      setLoading(false)
    }
  }

  return <div className="auth-shell"><div className="auth-card"><div className="brand auth-brand"><div className="brand-mark">S</div><div><strong>SupportPilot</strong><span>企业客服工作台</span></div></div><span className="panel-kicker">SECURE ACCESS</span><h1>{mode === 'login' ? '欢迎回来' : '创建首个管理员账号'}</h1><p className="auth-description">{mode === 'login' ? '登录后访问订单、工单、知识库和审批能力。' : '首次部署时创建的账号将自动获得管理员权限。'}</p><form className="business-form auth-form" onSubmit={submit}>{mode === 'register' && <label>显示名称<input required value={displayName} onChange={(event) => setDisplayName(event.target.value)} placeholder="例如：陈客服" /></label>}<label>邮箱<input required type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="name@company.com" /></label><label>密码<input required type="password" minLength={8} value={password} onChange={(event) => setPassword(event.target.value)} placeholder="至少 8 位" /></label>{error && <div className="auth-error">{error}</div>}<button className="primary-button" type="submit" disabled={loading}>{loading ? '处理中…' : mode === 'login' ? '登录工作台' : '创建管理员账号'}</button></form><button className="auth-switch" onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError('') }}>{mode === 'login' ? '首次部署？创建管理员账号' : '已有账号？返回登录'}</button></div></div>
}

function StatusTag({ value }: { value: string }) {
  return <span className={`status-tag ${value === '已解决' || value === '已签收' ? 'success' : value === '处理中' || value === '运输中' ? 'info' : 'warning'}`}>{value}</span>
}

function EmptyState({ text }: { text: string }) {
  return <div className="empty-state">{text}</div>
}

function OrderSummary({ order, onWorkflow }: { order: Order; onWorkflow: (orderId: string) => void }) {
  return <div><div className="order-id-row"><strong>{order.order_id}</strong><StatusTag value={order.shipping_status} /></div><div className="order-grid"><div><span>客户</span><strong>{order.customer_name}</strong></div><div><span>商品</span><strong>{order.product_name}</strong></div><div><span>支付状态</span><strong>{order.payment_status}</strong></div><div><span>付款时长</span><strong>{order.hours_since_payment} 小时</strong></div><div><span>预计送达</span><strong>{order.estimated_delivery}</strong></div></div><button className="workflow-button" onClick={() => onWorkflow(order.order_id)}>运行物流异常工作流 →</button></div>
}

function ApprovalCard({ approval, onDecision }: { approval: PendingApproval | null; onDecision: (decision: 'approve' | 'reject') => void }) {
  if (!approval) return <div className="panel approval-panel"><div className="panel-header compact"><div><span className="panel-kicker">HUMAN IN THE LOOP</span><h2>审批中心</h2></div></div><EmptyState text="当前没有待审批动作" /></div>
  return <div className="panel approval-panel"><div className="panel-header compact"><div><span className="panel-kicker">HUMAN IN THE LOOP</span><h2>审批中心</h2></div><span className={`approval-state ${approval.status}`}>{approval.status === 'pending' ? '需要主管审批' : approval.status === 'approved' ? '已批准' : '已拒绝'}</span></div><div className="approval-body"><div className="approval-icon">!</div><div><strong>{approval.action}</strong><span>{approval.target}</span></div></div><p className="approval-reason">{approval.reason}</p><div className="approval-meta">审批编号：{approval.approvalId}</div><div className="approval-actions"><button className="reject-button" disabled={approval.status !== 'pending'} onClick={() => onDecision('reject')}>拒绝</button><button className="approve-button" disabled={approval.status !== 'pending'} onClick={() => onDecision('approve')}>批准执行</button></div></div>
}

export default App
