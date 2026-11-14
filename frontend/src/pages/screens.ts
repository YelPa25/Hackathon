import { Activity, History, BookOpen, Orbit } from 'lucide-react'

export const screens = [
  {
    path: '/',
    title: 'Mission Overview',
    icon: Orbit,
    description: 'Crew and cabin conditions in one view.',
    empty: 'No mission data loaded',
    detail: 'Crew summaries and cabin readings will appear after the historical dataset is imported.',
  },
  {
    path: '/crew-health',
    title: 'Crew Health',
    icon: Activity,
    description: 'Individual measurements, history and personal baselines.',
    empty: 'No crew profiles loaded',
    detail: 'Crew profiles and readings will appear after the historical dataset is imported.',
  },
  {
    path: '/mission-replay',
    title: 'Mission Replay',
    icon: History,
    description: 'A chronological view of revealed mission observations.',
    empty: 'Replay is unavailable',
    detail: 'Replay will begin at the end of Day 45 once the history and replay engine are ready.',
  },
  {
    path: '/data-and-science',
    title: 'Data & Science',
    icon: BookOpen,
    description: 'Dataset provenance, measurement definitions and research sources.',
    empty: 'No dataset loaded',
    detail: 'ASTRA is designed for research-informed synthetic observations. Dataset details will appear after import.',
  },
] as const
