import { Activity, History, BookOpen, Orbit } from 'lucide-react'

export const screens = [
  {
    path: '/',
    title: 'Mission Overview',
    icon: Orbit,
    description: 'Crew and cabin conditions in one view.',
  },
  {
    path: '/crew-health',
    title: 'Crew Health',
    icon: Activity,
    description: 'Individual measurements and their recorded history.',
  },
  {
    path: '/mission-replay',
    title: 'Mission Replay',
    icon: History,
    description: 'Published mission time and observation availability.',
  },
  {
    path: '/data-and-science',
    title: 'Data & Science',
    icon: BookOpen,
    description: 'Dataset provenance, measurement definitions and research sources.',
  },
] as const
