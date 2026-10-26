import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

/**
 * Every assistant reply goes through here. The agent returns **bold**, bullet
 * lists and links; dropping that into a text node shows literal asterisks.
 *
 * The .md styles in styles.css give it real paragraph spacing, so there is no
 * white-space: pre-wrap on this container (that would double the gaps).
 */
export default function Markdown({ children }: { children: string }) {
  return (
    <div className="md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  )
}
