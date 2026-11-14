import { createContext, useContext } from 'react'
import type { ReplayAction, ReplaySpeed, ReplayView } from './mission'

export const ReplayContext = createContext<{
  state?: ReplayView
  error?: string
  pending: boolean
  offline: boolean
  send: (action: ReplayAction, speed?: ReplaySpeed) => Promise<void>
} | null>(null)

export function useReplay() {
  const context = useContext(ReplayContext)
  if (!context) throw new Error('Replay state is unavailable outside the mission console.')
  return context
}
