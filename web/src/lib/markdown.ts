// Markdown 渲染：禁用原始 HTML，渲染后经 DOMPurify 净化；[n] 引用标记转为可点击引用按钮。
import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'

const md = new MarkdownIt({ html: false, linkify: true, breaks: true })

// 表格外包一层可横向滚动的容器（表头吸顶、斑马纹见 style.css .table-wrap）
md.renderer.rules.table_open = () => '<div class="table-wrap"><table>\n'
md.renderer.rules.table_close = () => '</table></div>\n'

export type MdSegment = { kind: 'md'; text: string } | { kind: 'chart'; raw: string }

/** 把 ```chart 代码块拆出来单独渲染为图表，其余部分按 Markdown 渲染 */
export function splitCharts(text: string): MdSegment[] {
  const out: MdSegment[] = []
  const re = /^```chart[^\n]*\n([\s\S]*?)^```[ \t]*$/gm
  let last = 0
  for (let m = re.exec(text); m; m = re.exec(text)) {
    if (m.index > last) out.push({ kind: 'md', text: text.slice(last, m.index) })
    out.push({ kind: 'chart', raw: m[1] })
    last = m.index + m[0].length
  }
  if (last < text.length) out.push({ kind: 'md', text: text.slice(last) })
  return out.filter((s) => s.kind === 'chart' || s.text.trim())
}

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
