import axios from 'axios'
import type {User} from './types'

const baseURL = import.meta.env.VITE_API_BASE_URL || '/api'
export const api = axios.create({baseURL, withCredentials: true, timeout: baseURL.startsWith('https://') ? 75000 : 15000})
export type Session = {user: User; csrf_token: string}
type ErrorBody = {detail?: string; errors?: {field: string; message: string}[]}

export function statusOf(error: unknown) {
  return axios.isAxiosError(error) ? error.response?.status : undefined
}

export function describe(error: unknown) {
  if (axios.isAxiosError<ErrorBody>(error)) {
    const data = error.response?.data
    if (data?.errors?.length) {
      return data.errors.map(({field, message}) =>
        (field === 'body' ? '' : field.replaceAll('_', ' ') + ' — ') + message.replace(/^Value error, /, '')
      ).join('. ')
    }
    return data?.detail || 'Could not reach the server. Please try again.'
  }
  return 'Something went wrong. Please try again.'
}

export function setCsrf(token?: string) {
  if (token) api.defaults.headers.common['X-CSRF-Token'] = token
  else delete api.defaults.headers.common['X-CSRF-Token']
}
