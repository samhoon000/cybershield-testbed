import {useCallback, useEffect, useState} from 'react'
import {api, describe} from './api'

export function useApi<T>(url: string | null) {
  const [revision, setRevision] = useState(0)
  const [result, setResult] = useState<{url: string; data?: T; error?: string}>()
  const refresh = useCallback(() => {
    setResult(undefined)
    setRevision(value => value + 1)
  }, [])
  useEffect(() => {
    if (!url) return
    const controller = new AbortController()
    api.get<T>(url, {signal: controller.signal}).then(({data}) => {
      if (!controller.signal.aborted) setResult({url, data})
    }).catch(error => {
      if (!controller.signal.aborted) setResult({url, error: describe(error)})
    })
    return () => controller.abort()
  }, [url, revision])

  const current = url && result?.url === url ? result : undefined
  return {data: current?.data, error: current?.error, loading: Boolean(url && !current), refresh}
}
