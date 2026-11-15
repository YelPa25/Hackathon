import { Fragment } from 'react'

// Render small text-only Markdown structures. Model output never becomes HTML or external links.
function inline(text: string) {
  return text.split(/(\*\*[^*\n]+\*\*|`[^`\n]+`)/g).map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**')) return <strong key={index}>{part.slice(2, -2)}</strong>
    if (part.startsWith('`') && part.endsWith('`')) return <code key={index}>{part.slice(1, -1)}</code>
    return <Fragment key={index}>{part}</Fragment>
  })
}

const ordered = /^\d+[.)]\s+/
const bullet = /^[-*]\s+/
const heading = /^#{1,6}\s+/

export function ReplyText({ text }: { text: string }) {
  return <div className="companion-rich-text">{text.split(/\n\s*\n/).map((block, index) => {
    const lines = block.split('\n').map((line) => line.trim()).filter(Boolean)
    if (lines.length && lines.every((line) => ordered.test(line))) {
      return <ol key={index}>{lines.map((line, item) => <li key={item}>{inline(line.replace(ordered, ''))}</li>)}</ol>
    }
    if (lines.length && lines.every((line) => bullet.test(line))) {
      return <ul key={index}>{lines.map((line, item) => <li key={item}>{inline(line.replace(bullet, ''))}</li>)}</ul>
    }
    return <p key={index}>{block.split('\n').map((line, item) => <Fragment key={item}>
      {item > 0 && <br />}{heading.test(line) ? <strong>{inline(line.replace(heading, ''))}</strong> : inline(line)}
    </Fragment>)}</p>
  })}</div>
}
