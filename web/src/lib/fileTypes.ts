// 上传文件：允许的类型、按扩展名的图标/配色、解析状态文案。
import { FileImage, FileSpreadsheet, FileText, FileType2, Presentation, File as FileIcon, FileCode } from 'lucide-vue-next'
import type { Component } from 'vue'
import type { FileParseStatus } from '@/api/types'

export const ALLOWED_EXT = new Set([
  'pdf', 'docx', 'doc', 'xlsx', 'xlsm', 'xls', 'csv', 'tsv', 'ppt', 'pptx',
  'png', 'jpg', 'jpeg', 'webp', 'bmp', 'gif', 'tif', 'tiff', 'jp2',
  'txt', 'md', 'markdown', 'json', 'log', 'xml', 'yaml', 'yml', 'html', 'htm',
  'rtf', 'odt', 'ods', 'odp', 'epub', 'ofd', 'mhtml', 'mht',
])
export const ACCEPT = [...ALLOWED_EXT].map((e) => `.${e}`).join(',')
export const MAX_FILE_MB = 100
export const MAX_FILES = 10

export type Tone = 'mint' | 'lilac' | 'butter' | 'sky' | 'peach' | 'plain'

export interface FileKind {
  label: string
  tone: Tone
  icon: Component
}

export function extOf(name: string): string {
  const i = name.lastIndexOf('.')
  return i >= 0 ? name.slice(i + 1).toLowerCase() : ''
}

export function fileKind(ext: string): FileKind {
  const e = ext.toLowerCase()
  if (e === 'pdf' || e === 'ofd') return { label: e.toUpperCase(), tone: 'peach', icon: FileType2 }
  if (['doc', 'docx', 'rtf', 'odt', 'epub'].includes(e)) return { label: 'Word', tone: 'sky', icon: FileText }
  if (['xls', 'xlsx', 'xlsm', 'csv', 'tsv', 'ods'].includes(e))
    return { label: e === 'csv' || e === 'tsv' ? e.toUpperCase() : 'Excel', tone: 'mint', icon: FileSpreadsheet }
  if (['ppt', 'pptx', 'odp'].includes(e)) return { label: 'PPT', tone: 'butter', icon: Presentation }
  if (['png', 'jpg', 'jpeg', 'webp', 'bmp', 'gif', 'tif', 'tiff', 'jp2'].includes(e))
    return { label: '图片', tone: 'lilac', icon: FileImage }
  if (['html', 'htm', 'mhtml', 'mht', 'json', 'xml', 'yaml', 'yml'].includes(e))
    return { label: e.toUpperCase(), tone: 'plain', icon: FileCode }
  if (['txt', 'md', 'markdown', 'log'].includes(e)) return { label: e === 'txt' ? '文本' : 'Markdown', tone: 'plain', icon: FileText }
  return { label: e.toUpperCase() || '文件', tone: 'plain', icon: FileIcon }
}

/** 长文件名中间省略：保留开头与扩展名 */
export function middleTruncate(name: string, max = 26): string {
  if (name.length <= max) return name
  const dot = name.lastIndexOf('.')
  const ext = dot > 0 && name.length - dot <= 8 ? name.slice(dot) : ''
  const head = Math.max(6, max - ext.length - 4)
  return `${name.slice(0, head)}…${name.slice(name.length - ext.length - 3)}`
}

export const PARSE_LABEL: Record<FileParseStatus, string> = {
  queued: '排队解析',
  parsing: '解析中',
  parsed: '已解析',
  failed: '解析失败',
}

/** 解析器的简短名称（用于“已解析 · 12 页 · MinerU”） */
export function parserShort(parser: string | null | undefined): string {
  if (!parser) return ''
  return parser.startsWith('mineru') ? 'MinerU' : parser === 'builtin' ? '内置解析' : parser
}

/** 引用/来源里的 file:<id>#<k> → 文件 ID */
export function fileIdFromUrl(url: string | null | undefined): string | null {
  const m = /^file:([^#]+)/.exec(url || '')
  return m ? m[1] : null
}

export const MINERU_HINT = '扫描件、图片、PPT 需要管理员配置 MinerU（config.yaml 的 mineru.api_url 或 mineru.cloud_token）'

/** 状态说明：“已解析 · 12 页 · MinerU” */
export function statusLine(
  status: string,
  opts: { pages?: number | null; parser?: string | null; progress?: number; error?: string | null } = {},
): string {
  switch (status) {
    case 'uploading':
      return `上传中 ${opts.progress ?? 0}%`
    case 'upload_failed':
      return opts.error || '上传失败'
    case 'queued':
      return '排队解析'
    case 'parsing':
      return '解析中…'
    case 'parsed':
      return ['已解析', opts.pages ? `${opts.pages} 页` : '', parserShort(opts.parser)].filter(Boolean).join(' · ')
    case 'failed':
      return '解析失败'
    default:
      return status
  }
}

export function formatSize(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(n < 10 * 1024 ? 1 : 0)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}
