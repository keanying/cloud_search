// Markdown 渲染：禁用原始 HTML，渲染后经 DOMPurify 净化；[n] 引用标记转为可点击引用按钮。
import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'

const md = new MarkdownIt({ html: false, linkify: true, breaks: true })

DOMPurify.addHook('afterSanitizeAttributes', (node) => {
  if (node.tagName === 'A') {
    node.setAttribute('target', '_blank')
    node.setAttribute('rel', 'noopener noreferrer nofollow')
  }
})

/** 仅替换标签外文本中的 [n]，且只替换存在于 validNs 的编号 */
function linkCitations(html: string, validNs: Set<number> | null): string {
  return html.replace(/(<[^>]*>)|\[(\d{1,3})\]/g, (m, tag: string | undefined, num: string | undefined) => {
    if (tag) return tag
    const n = Number(num)
    if (validNs && !validNs.has(n)) return m
    return `<button type="button" class="cite-chip" data-cite="${n}" aria-label="查看来源 ${n}">${n}</button>`
  })
}

export function renderMarkdown(text: string, citationNs?: number[] | null): string {
  const raw = md.render(text || '')
  const withCites = citationNs && citationNs.length ? linkCitations(raw, new Set(citationNs)) : raw
  return DOMPurify.sanitize(withCites, { ADD_ATTR: ['target', 'data-cite'] })
}

export function renderMarkdownPlain(text: string): string {
  return DOMPurify.sanitize(md.render(text || ''), { ADD_ATTR: ['target'] })
}
