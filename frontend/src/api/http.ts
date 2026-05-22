import axios from 'axios'

const http = axios.create({
  baseURL: '/api',
  timeout: 10000,
  headers: { 'Content-Type': 'application/json' },
})

http.interceptors.response.use(
  (resp) => {
    const body = resp.data
    if (body && typeof body === 'object' && 'success' in body) {
      if (body.success === false) {
        const message = body.error?.message ?? 'unknown error'
        return Promise.reject(new Error(message))
      }
      return body.data
    }
    return body
  },
  (err) => {
    const message = err.response?.data?.error?.message ?? err.message ?? 'network error'
    return Promise.reject(new Error(message))
  },
)

export default http
