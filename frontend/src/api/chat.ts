/** Chat API — RAG + GraphRAG 问答端点。 */

import http from './http'

// ─── 类型 ────────────────────────────────────────────────────────────────

export interface ChatSource {
  type?: string
  source?: string
  title?: string
  similarity?: number
  relevance?: number
  snippet?: string
}

export interface RAGQueryResponse {
  answer: string
  sources: ChatSource[]
  tokens_used: number
  results_count: number
  retrieval_mode?: 'hybrid' | 'vector' | 'bm25' | 'none'
}

export interface GraphQueryResponse {
  answer: string
  sources: ChatSource[]
  search_mode: string
  search_results: Array<{
    type: string
    relevance: number
    content: string
  }>
  tokens_used?: number
}

// ─── API 函数 ────────────────────────────────────────────────────────────

/** 标准 RAG 问答（向量 + 混合检索 + 重排序）。 */
export function queryRAG(
  question: string,
  history?: Array<{ role: string; content: string }>,
  collection: string = 'dc_knowledge',
): Promise<RAGQueryResponse> {
  return http.post('/rag/query', { question, history, collection }, { timeout: 120000 })
}

/** GraphRAG 图谱问答（global / local / basic 自动路由）。 */
export function queryGraph(
  question: string,
  topK?: number,
): Promise<GraphQueryResponse> {
  return http.post('/graph/query', { question, top_k: topK }, { timeout: 120000 })
}

/** RAG 向量库状态。 */
export function getRAGStatus(): Promise<{
  collection_count: number
  embedding_model: string
  name: string
  storage_path: string
}> {
  return http.get('/rag/status')
}

/** GraphRAG 图谱索引状态。 */
export function getGraphStatus(): Promise<{
  built: boolean
  index: {
    entity_count: number
    relation_count: number
    community_count: number
    source_files: number
    summary: string
  } | null
  rebuild: { running: boolean; progress: string }
}> {
  return http.get('/graph/status')
}
