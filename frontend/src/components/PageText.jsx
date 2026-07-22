import { useMemo } from 'react'
import { segmentPage } from '../utils/formatText'
import { renderInline } from '../utils/arabic'

/**
 * Renders one page of a book from its raw text.
 *
 * The raw text is running prose with `***` standing in for the break between
 * the two hemistichs of a bayt; segmentPage() recovers the structure and this
 * component gives each block the shape it had on the printed page.
 */

function Html({ as: Tag = 'p', className, text, match }) {
  const html = useMemo(() => renderInline(text, match), [text, match])
  return <Tag className={className} dir="rtl" dangerouslySetInnerHTML={{ __html: html }} />
}

function Bayt({ block, match }) {
  const single = !block.sadr || !block.ajuz
  return (
    <div className={`blk bayt${single ? ' bayt--single' : ''}`}>
      <Html as="span" className="bayt__sadr" text={block.sadr || block.ajuz} match={match} />
      {!single && (
        <>
          <span className="bayt__rosette" aria-hidden="true">
            ۞
          </span>
          <Html as="span" className="bayt__ajuz" text={block.ajuz} match={match} />
        </>
      )}
      {(block.number || block.ref) && (
        <span className="bayt__meta">
          <span className="bayt__num">{block.number || ''}</span>
          <span className="bayt__ref">{block.ref || ''}</span>
        </span>
      )}
    </div>
  )
}

export default function PageText({ text, match, className = '' }) {
  const blocks = useMemo(() => segmentPage(text), [text])

  if (!blocks.length) {
    return (
      <p className="textblock text-center" style={{ color: 'var(--ink-faint)' }}>
        هذه الصفحة خالية من النص
      </p>
    )
  }

  return (
    <div className={`textblock ${className}`}>
      {blocks.map((block, i) => {
        switch (block.type) {
          case 'bayt':
            return <Bayt key={i} block={block} match={match} />
          case 'heading':
            return <Html key={i} as="h3" className="blk blk-heading" text={block.text} match={match} />
          case 'quote':
            return <Html key={i} className="blk blk-quote" text={block.text} match={match} />
          case 'folio':
            return (
              <p key={i} className="blk blk-folio">
                {block.text}
              </p>
            )
          case 'divider':
            return <div key={i} className="blk blk-divider" role="separator" />
          default:
            return <Html key={i} className="blk blk-para" text={block.text} match={match} />
        }
      })}
    </div>
  )
}
