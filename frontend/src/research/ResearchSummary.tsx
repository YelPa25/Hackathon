import { Link } from 'react-router'
import { detectorLabel, fixtureTime, modalityTitle } from './results'
import { useResearch } from './state'

export function ResearchSummary() {
  const { result } = useResearch()
  if (!result) return null

  const { modality, window, source, subject } = result
  return <section className="surface data-panel" aria-label="Experimental demonstration">
    <h2>Experimental demonstration</h2>
    <p><strong>{modalityTitle[modality]} · {detectorLabel[window.state]}</strong></p>
    <p>{source} · {subject} · <time dateTime={window.t}>{fixtureTime.format(new Date(window.t))} UTC</time></p>
    <Link className="return-link" to={'/research-prototypes?result=1#' + modality + '-' + result.view.kind}>View Research Prototypes</Link>
  </section>
}
