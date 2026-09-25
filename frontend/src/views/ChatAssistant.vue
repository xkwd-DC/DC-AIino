<script setup lang="ts">
/**
 * M06 · 稷韧云图 — 知识助手聊天页面
 *
 * 支持两种检索模式：
 *   RAG 标准检索 — 向量 + BM25 混合检索 + Reranker 重排序
 *   GraphRAG 深度图谱 — 知识图谱实体遍历 + 社区摘要
 */
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  queryGraph,
  queryRAG,
  type ChatSource,
  type GraphQueryResponse,
  type RAGQueryResponse,
} from '@/api/chat'

// ─── 类型 ────────────────────────────────────────────────────────────────

type SearchMode = 'rag' | 'graph'

interface Message {
  id: number
  role: 'user' | 'assistant'
  content: string
  sources?: ChatSource[]
  searchMode?: string
  tokensUsed?: number
  timestamp: number
}

// ─── 状态 ────────────────────────────────────────────────────────────────

const messages = ref<Message[]>([])
const inputText = ref('')
const isLoading = ref(false)
const searchMode = ref<SearchMode>('rag')
const ragScope = ref<'dc_knowledge' | 'dc_papers'>('dc_knowledge')
const errorMsg = ref('')
const messageList = ref<HTMLElement | null>(null)
const inputRef = ref<HTMLTextAreaElement | null>(null)

let nextId = 1

// ─── 建议问题 ────────────────────────────────────────────────────────────

const suggestions = [
  '华北平原冬小麦面临的主要气候风险有哪些？',
  'SHAP 分析揭示了哪些关键气候因子？',
  '当前文献中主要使用了哪些研究方法？',
  '极端高温对水稻产量的影响机制是什么？',
]

// ─── 格式化 ──────────────────────────────────────────────────────────────

const MODE_LABELS: Record<string, string> = {
  global: '全局综述',
  local: '图谱遍历',
  basic: '基础检索',
  rag: '混合检索',
  none: '未就绪',
}

function modeLabel(mode: string): string {
  return MODE_LABELS[mode] || mode
}

function renderMarkdown(text: string): string {
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>')
  html = html.replace(/【来源\s*(\d+)】/g, '<span class="source-tag">【来源 $1】</span>')
  html = html.replace(/\n/g, '<br>')
  return html
}

function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

// ─── 滚动 ────────────────────────────────────────────────────────────────

async function scrollToBottom() {
  await nextTick()
  if (messageList.value) {
    messageList.value.scrollTop = messageList.value.scrollHeight
  }
}

// ─── 发送消息 ────────────────────────────────────────────────────────────

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || isLoading.value) return

  errorMsg.value = ''
  inputText.value = ''

  const userMsg: Message = {
    id: nextId++, role: 'user', content: text, timestamp: Date.now(),
  }
  messages.value.push(userMsg)
  await scrollToBottom()

  isLoading.value = true

  try {
    const result = await queryByMode(text)
    messages.value.push({
      id: nextId++,
      role: 'assistant',
      content: result.answer,
      sources: result.sources,
      searchMode: result.searchMode,
      tokensUsed: result.tokensUsed,
      timestamp: Date.now(),
    })
  } catch (err: any) {
    errorMsg.value = err?.message || err?.toString() || '请求失败，请检查后端服务。'
  } finally {
    isLoading.value = false
    await scrollToBottom()
    inputRef.value?.focus()
  }
}

async function queryByMode(text: string): Promise<{
  answer: string; sources: ChatSource[]; searchMode: string; tokensUsed?: number
}> {
  if (searchMode.value === 'graph') {
    const res: GraphQueryResponse = await queryGraph(text)
    return {
      answer: res.answer,
      sources: res.sources,
      searchMode: res.search_mode,
      tokensUsed: res.tokens_used,
    }
  }

  const history = messages.value
    .filter((m) => m.role === 'user' || m.role === 'assistant')
    .slice(-8)
    .map((m) => ({ role: m.role, content: m.content }))

  const res: RAGQueryResponse = await queryRAG(text, history, ragScope.value)
  return {
    answer: res.answer,
    sources: res.sources,
    searchMode: 'rag',
    tokensUsed: res.tokens_used,
  }
}

// ─── 键盘 ────────────────────────────────────────────────────────────────

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}

function onInput() {
  const el = inputRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 160) + 'px'
}

// ─── 快捷操作 ────────────────────────────────────────────────────────────

function clearChat() {
  messages.value = []
  errorMsg.value = ''
}

function useSuggestion(text: string) {
  inputText.value = text
  inputRef.value?.focus()
}

// ─── 生命周期 ────────────────────────────────────────────────────────────

onMounted(() => { inputRef.value?.focus() })
onBeforeUnmount(() => { /* noop */ })
</script>

<template>
  <section class="page chat-page" aria-label="知识助手聊天">
    <header class="page-head">
      <div class="eyebrow">M06 · KNOWLEDGE ASSISTANT</div>
      <h2>稷韧云图 · 知识助手</h2>
      <p class="lead">
        AI 驱动的文献知识问答。支持 RAG 标准检索与 GraphRAG 图谱深度推理。
      </p>
    </header>

    <!-- 工具栏 -->
    <div class="chat-toolbar">
      <div class="mode-switch" role="radiogroup" aria-label="检索模式">
        <button
          type="button"
          class="mode-btn"
          :class="{ active: searchMode === 'rag' }"
          role="radio"
          :aria-checked="searchMode === 'rag'"
          @click="searchMode = 'rag'"
        >
          <span class="mode-icon">🔍</span>
          <span class="mode-label">标准检索</span>
          <span class="mode-desc">向量 + 关键词</span>
        </button>
        <button
          type="button"
          class="mode-btn"
          :class="{ active: searchMode === 'graph' }"
          role="radio"
          :aria-checked="searchMode === 'graph'"
          @click="searchMode = 'graph'"
        >
          <span class="mode-icon">🕸️</span>
          <span class="mode-label">深度图谱</span>
          <span class="mode-desc">知识图谱推理</span>
        </button>
      </div>

      <label v-if="searchMode === 'rag'" class="scope-select" aria-label="检索范围">
        <span class="scope-label">范围</span>
        <select v-model="ragScope" class="scope-dropdown">
          <option value="dc_knowledge">全库</option>
          <option value="dc_papers">论文</option>
        </select>
      </label>

      <button
        type="button"
        class="clear-btn"
        :disabled="messages.length === 0"
        @click="clearChat"
        aria-label="清空对话"
      >
        清空对话
      </button>
    </div>

    <!-- 消息列表 -->
    <div
      ref="messageList"
      class="message-list"
      role="log"
      aria-live="polite"
      aria-label="对话记录"
    >
      <!-- 空状态 -->
      <div v-if="messages.length === 0 && !isLoading" class="empty-state">
        <div class="empty-icon">🌾</div>
        <p class="empty-title">开始探索 DC 知识库</p>
        <p class="empty-desc">
          向我提问关于极端气候、粮食生产风险、研究方法等任何问题。
        </p>
        <div class="suggestions">
          <button
            v-for="s in suggestions"
            :key="s"
            type="button"
            class="suggestion-chip"
            @click="useSuggestion(s)"
          >
            {{ s }}
          </button>
        </div>
      </div>

      <!-- 消息 -->
      <div
        v-for="msg in messages"
        :key="msg.id"
        class="message"
        :class="`message--${msg.role}`"
      >
        <div class="message-avatar" :aria-label="msg.role === 'user' ? '你' : '稷韧云图'">
          {{ msg.role === 'user' ? '👤' : '🌾' }}
        </div>
        <div class="message-body">
          <div class="message-meta">
            <span class="message-role">
              {{ msg.role === 'user' ? '你' : '稷韧云图' }}
            </span>
            <span
              v-if="msg.searchMode && msg.role === 'assistant'"
              class="mode-badge"
              :class="`badge--${msg.searchMode}`"
            >
              {{ modeLabel(msg.searchMode) }}
            </span>
            <span class="message-time">{{ formatTime(msg.timestamp) }}</span>
          </div>
          <!-- eslint-disable-next-line vue/no-v-html -->
          <div class="message-text" v-html="renderMarkdown(msg.content)" />

          <!-- 来源引用 -->
          <div
            v-if="msg.sources && msg.sources.length > 0 && msg.role === 'assistant'"
            class="sources"
          >
            <details class="sources-details">
              <summary class="sources-summary">
                查看来源 ({{ msg.sources.length }})
                <span v-if="msg.tokensUsed" class="tokens-info">
                  · {{ msg.tokensUsed }} tokens
                </span>
              </summary>
              <ul class="sources-list">
                <li v-for="(src, i) in msg.sources" :key="i" class="source-item">
                  <span class="source-index">{{ i + 1 }}</span>
                  <div class="source-body">
                    <div class="source-title">
                      {{ src.title || src.source || src.type || '未知来源' }}
                    </div>
                    <p v-if="src.snippet" class="source-snippet">{{ src.snippet }}</p>
                    <span v-if="src.similarity" class="source-score">
                      相似度 {{ (src.similarity * 100).toFixed(0) }}%
                    </span>
                    <span v-if="src.relevance" class="source-score">
                      相关度 {{ (src.relevance * 100).toFixed(0) }}%
                    </span>
                  </div>
                </li>
              </ul>
            </details>
          </div>
        </div>
      </div>

      <!-- 加载指示器 -->
      <div v-if="isLoading" class="message message--assistant">
        <div class="message-avatar" aria-label="思考中">🌾</div>
        <div class="message-body">
          <div class="typing-indicator">
            <span class="typing-dot" />
            <span class="typing-dot" />
            <span class="typing-dot" />
            <span class="typing-text">正在检索知识库...</span>
          </div>
        </div>
      </div>

      <!-- 错误横幅 -->
      <div v-if="errorMsg" class="error-banner" role="alert">
        <span class="error-icon">⚠️</span>
        <span>{{ errorMsg }}</span>
        <button type="button" class="error-dismiss" @click="errorMsg = ''" aria-label="关闭">×</button>
      </div>
    </div>

    <!-- 输入区 -->
    <div class="input-area">
      <textarea
        ref="inputRef"
        v-model="inputText"
        class="chat-input"
        :disabled="isLoading"
        placeholder="输入问题，Enter 发送，Shift+Enter 换行..."
        rows="1"
        aria-label="输入问题"
        @keydown="onKeydown"
        @input="onInput"
      />
      <button
        type="button"
        class="send-btn"
        :disabled="!inputText.trim() || isLoading"
        @click="sendMessage"
        aria-label="发送"
      >
        <span v-if="!isLoading" class="send-icon">↑</span>
        <span v-else class="send-icon spin">⏳</span>
      </button>
    </div>
  </section>
</template>

<style scoped>
/* ─── 页面布局 ────────────────────────────────────────────────────────── */
.chat-page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 80px);
  max-width: 900px;
  margin: 0 auto;
  padding: 24px 32px 0;
}

/* ─── 工具栏 ──────────────────────────────────────────────────────────── */
.chat-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 0 16px;
  gap: 12px;
  flex-shrink: 0;
}

.mode-switch {
  display: flex;
  gap: 4px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  padding: 4px;
}

.mode-btn {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 8px 16px;
  border: none;
  border-radius: var(--r-md);
  background: transparent;
  color: var(--text-3);
  cursor: pointer;
  transition: all var(--dur-fast) var(--ease-out);
  font-family: inherit;
  font-size: 13px;
  line-height: 1.3;
}

.mode-btn:hover { color: var(--text); background: var(--bg-elev); }

.mode-btn.active { background: var(--green-deep); color: var(--green-bright); }

.mode-icon { font-size: 16px; }

.mode-label { font-weight: 600; font-family: var(--font-sans); }

.mode-desc { font-size: 11px; opacity: 0.7; }

.scope-select {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  background: var(--bg-card);
  font-size: 12px;
  color: var(--text-3);
}

.scope-label { font-size: 12px; opacity: 0.85; }

.scope-dropdown {
  appearance: none;
  border: none;
  background: transparent;
  color: var(--text);
  font-family: inherit;
  font-size: 12px;
  padding: 0 4px;
  cursor: pointer;
}

.scope-dropdown:focus { outline: none; }

.clear-btn {
  padding: 6px 14px;
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  background: transparent;
  color: var(--text-3);
  cursor: pointer;
  font-size: 12px;
  font-family: inherit;
  transition: all var(--dur-fast) var(--ease-out);
}

.clear-btn:hover:not(:disabled) { border-color: var(--red); color: var(--red); }

.clear-btn:disabled { opacity: 0.3; cursor: not-allowed; }

/* ─── 消息列表 ────────────────────────────────────────────────────────── */
.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 0 24px;
  scroll-behavior: smooth;
}

.message-list::-webkit-scrollbar { width: 4px; }

.message-list::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

/* ─── 空状态 ──────────────────────────────────────────────────────────── */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  text-align: center;
}

.empty-icon { font-size: 48px; margin-bottom: 16px; }

.empty-title { font-family: var(--font-serif); font-size: 20px; color: var(--text); margin: 0 0 8px; }

.empty-desc { font-size: 14px; color: var(--text-3); margin: 0 0 24px; }

.suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  max-width: 560px;
}

.suggestion-chip {
  padding: 8px 16px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  color: var(--text-2);
  font-size: 13px;
  font-family: inherit;
  cursor: pointer;
  transition: all var(--dur-fast) var(--ease-out);
}

.suggestion-chip:hover {
  border-color: var(--green);
  color: var(--green-bright);
  background: var(--bg-elev);
}

/* ─── 消息气泡 ────────────────────────────────────────────────────────── */
.message {
  display: flex;
  gap: 12px;
  padding: 12px 0;
  animation: fadeUp 0.3s var(--ease-out);
}

.message--user { flex-direction: row-reverse; }

.message-avatar {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  border-radius: var(--r-full, 50%);
  background: var(--bg-card);
  border: 1px solid var(--border);
}

.message-body { max-width: 75%; min-width: 100px; }

.message--user .message-body { display: flex; flex-direction: column; align-items: flex-end; }

.message-meta { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; font-size: 11px; }

.message-role { color: var(--text-3); font-family: var(--font-sans); font-weight: 600; }

.message-time { color: var(--text-3); opacity: 0.6; }

.mode-badge {
  padding: 1px 8px;
  border-radius: var(--r-sm);
  font-size: 10px;
  font-family: var(--font-mono);
  font-weight: 600;
  text-transform: uppercase;
}

.badge--global { background: rgba(100, 180, 255, 0.15); color: #64b4ff; }
.badge--local  { background: rgba(160, 220, 120, 0.15); color: #a0dc78; }
.badge--basic  { background: rgba(180, 180, 180, 0.15); color: var(--text-3); }
.badge--rag    { background: rgba(100, 220, 180, 0.15); color: var(--green-bright); }
.badge--none   { background: rgba(255, 160, 80, 0.15); color: var(--amber); }

.message-text {
  padding: 10px 16px;
  border-radius: var(--r-lg);
  font-size: 14px;
  line-height: 1.7;
  color: var(--text);
  word-break: break-word;
}

.message--user .message-text {
  background: var(--green-deep);
  color: #e0f0e8;
  border-bottom-right-radius: 4px;
}

.message--assistant .message-text {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-bottom-left-radius: 4px;
}

.message-text :deep(strong) { color: var(--green-bright); font-weight: 600; }

.message-text :deep(.inline-code) {
  padding: 1px 5px;
  background: var(--bg-elev);
  border-radius: var(--r-sm);
  font-family: var(--font-mono);
  font-size: 0.9em;
}

.message-text :deep(.source-tag) { color: var(--green); font-weight: 600; font-size: 0.85em; }

/* ─── 来源引用 ────────────────────────────────────────────────────────── */
.sources { margin-top: 8px; }

.sources-details { font-size: 12px; }

.sources-summary { color: var(--text-3); cursor: pointer; user-select: none; padding: 4px 0; transition: color var(--dur-fast); }

.sources-summary:hover { color: var(--green); }

.tokens-info { opacity: 0.6; font-family: var(--font-mono); }

.sources-list { list-style: none; margin: 8px 0 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }

.source-item {
  display: flex;
  gap: 10px;
  padding: 8px 12px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
}

.source-index {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--green-deep);
  color: var(--green-bright);
  border-radius: var(--r-sm);
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
}

.source-body { flex: 1; min-width: 0; }

.source-title { font-weight: 600; color: var(--text); margin-bottom: 2px; }

.source-snippet {
  color: var(--text-3);
  font-size: 12px;
  margin: 2px 0;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-height: 1.5;
}

.source-score {
  display: inline-block;
  margin-top: 2px;
  padding: 1px 6px;
  background: var(--bg-card);
  border-radius: var(--r-sm);
  color: var(--text-3);
  font-family: var(--font-mono);
  font-size: 10px;
}

/* ─── 输入区 ──────────────────────────────────────────────────────────── */
.input-area {
  display: flex;
  gap: 8px;
  padding: 16px 0 24px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
  background: var(--bg);
}

.chat-input {
  flex: 1;
  padding: 12px 16px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  color: var(--text);
  font-family: inherit;
  font-size: 14px;
  line-height: 1.5;
  resize: none;
  outline: none;
  transition: border-color var(--dur-fast) var(--ease-out);
}

.chat-input:focus { border-color: var(--green); box-shadow: 0 0 0 2px rgba(100, 200, 100, 0.15); }

.chat-input:disabled { opacity: 0.5; }

.chat-input::placeholder { color: var(--text-3); opacity: 0.5; }

.send-btn {
  flex-shrink: 0;
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: var(--r-lg);
  background: var(--green-deep);
  color: var(--green-bright);
  cursor: pointer;
  font-size: 18px;
  transition: all var(--dur-fast) var(--ease-out);
  align-self: flex-end;
}

.send-btn:hover:not(:disabled) { background: var(--green); color: var(--bg); }

.send-btn:disabled { opacity: 0.3; cursor: not-allowed; }

.send-icon { display: block; line-height: 1; }

.spin { animation: spin 1s linear infinite; }

@keyframes spin { to { transform: rotate(360deg); } }

/* ─── 输入指示器 ──────────────────────────────────────────────────────── */
.typing-indicator { display: flex; align-items: center; gap: 6px; padding: 12px 16px; }

.typing-dot {
  width: 6px;
  height: 6px;
  background: var(--green);
  border-radius: 50%;
  animation: typingBounce 1.4s ease-in-out infinite;
}

.typing-dot:nth-child(2) { animation-delay: 0.2s; }
.typing-dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes typingBounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
  30% { transform: translateY(-6px); opacity: 1; }
}

.typing-text { margin-left: 6px; font-size: 13px; color: var(--text-3); }

/* ─── 错误横幅 ────────────────────────────────────────────────────────── */
.error-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  margin: 8px 0;
  background: rgba(255, 120, 80, 0.1);
  border: 1px solid rgba(255, 120, 80, 0.3);
  border-radius: var(--r-md);
  color: var(--red);
  font-size: 13px;
}

.error-icon { flex-shrink: 0; }

.error-dismiss { margin-left: auto; border: none; background: none; color: var(--red); font-size: 18px; cursor: pointer; padding: 0 4px; }

/* ─── 响应式 ──────────────────────────────────────────────────────────── */
@media (max-width: 768px) {
  .chat-page { padding: 16px 16px 0; height: calc(100vh - 72px); }
  .message-body { max-width: 85%; }
  .mode-btn { padding: 6px 12px; }
  .mode-desc { display: none; }
  .suggestions { flex-direction: column; align-items: stretch; }
}
</style>
