// 成果多格式：标签、文件名与下载
import type { ArtifactFormat, ArtifactFormatName, ArtifactPart } from '@/api/types'
import { api } from '@/api/client'

export const FORMAT_LABEL: Record<ArtifactFormatName, string> = {
  docx: 'Word',
  pdf: 'PDF',
  html: 'HTML',
  md: 'Markdown',
  xlsx: 'Excel',
  csv: 'CSV',
  json: 'JSON',
}

const ORDER: ArtifactFormatName[] = ['docx', 'pdf', 'xlsx', 'html', 'csv', 'md', 'json']

/** 文件名：主文件名去掉扩展名后加上该格式的扩展名 */
export function formatFileName(displayName: string, f: ArtifactFormatName): string {
  const base = displayName.replace(/\.[A-Za-z0-9]{1,5}$/, '')
  return `${base}.${f}`
}

/** 该成果的全部格式（包含主文件；兼容没有 formats 的旧数据） */
export function partFormats(p: ArtifactPart): ArtifactFormat[] {
  const list = [...(p.formats ?? [])]
  if (!list.some((f) => f.artifact_id === p.artifact_id)) {
    const ext = (p.display_name.match(/\.([A-Za-z0-9]{1,5})$/)?.[1] ?? '').toLowerCase() as ArtifactFormatName
    if (ext in FORMAT_LABEL) list.push({ format: ext, artifact_id: p.artifact_id, byte_qty: p.byte_qty })
  }
  return list.sort((a, b) => ORDER.indexOf(a.format) - ORDER.indexOf(b.format))
}

/** 预览优先用 HTML 版本（与下载的排版一致） */
export function previewArtifactId(p: ArtifactPart): string {
  return p.formats?.find((f) => f.format === 'html')?.artifact_id ?? p.artifact_id
}

export async function downloadFormat(p: { display_name: string }, f: ArtifactFormat) {
  await api.downloadArtifact(f.artifact_id, formatFileName(p.display_name, f.format))
}
