import { useEffect, useState } from 'react'

export type Connection = 'checking' | 'connected' | 'storage-unavailable' | 'unavailable'

export function useHealth() {
  const [connection, setConnection] = useState<Connection>('checking')

  useEffect(() => {
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout>

    async function check() {
      let next: Connection = 'unavailable'
      try {
        const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(2500)])
        const response = await fetch('/api/health', {
          cache: 'no-store',
          headers: { Accept: 'application/json' },
          signal,
        })
        const data = await response.json()
        if (response.ok && data?.status === 'ok' && data.database_ready === true) {
          next = 'connected'
        } else if (response.status === 503 && data?.status === 'unavailable' && data.database_ready === false) {
          next = 'storage-unavailable'
        }
      } catch {
        // A timeout, network error or unreadable response leaves the service unavailable.
      }
      if (!controller.signal.aborted) {
        setConnection(next)
        timer = setTimeout(check, 3000)
      }
    }

    void check()
    return () => {
      controller.abort()
      clearTimeout(timer)
    }
  }, [])

  return connection
}
