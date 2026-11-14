import { Activity, History, BookOpen, Orbit, FlaskConical } from 'lucide-react'

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
  {
    path: '/research-prototypes',
    title: 'Research Prototypes',
    icon: FlaskConical,
    description: 'Facial and acoustic feature monitoring demonstrations.',
  },
] as const
