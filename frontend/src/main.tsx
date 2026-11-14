import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import { ReplayProvider } from './app/ReplayProvider'
import { App } from './app/App'
import { ResearchProvider } from './research/ResearchProvider'
import './styles/global.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <ReplayProvider><ResearchProvider><App /></ResearchProvider></ReplayProvider>
    </BrowserRouter>
  </StrictMode>,
)
