// 输入框附件：选择/拖放/粘贴后立即上传，跟踪上传进度与解析状态。
import { computed, ref } from 'vue'
import type { FileOut, FileParseStatus } from '@/api/types'
import { api } from '@/api/client'
import { useToastStore } from '@/stores/toast'
import { ALLOWED_EXT, MAX_FILES, MAX_FILE_MB, extOf } from './fileTypes'

export type AttachmentStatus = 'uploading' | 'upload_failed' | FileParseStatus

export interface Attachment {
  key: string
  name: string
  ext: string
  size: number
  status: AttachmentStatus
  progress: number
  error: string | null
  file: FileOut | null
  abort?: AbortController
}

let seq = 0

/** getConversationId：上传前确保有会话（首页会先创建会话） */
export function useAttachments(getConversationId: () => Promise<string>) {
  const items = ref<Attachment[]>([])
  const toast = useToastStore()

  const uploading = computed(() => items.value.some((a) => a.status === 'uploading'))
  /** 可随消息发送的文件（已上传；解析中也可以，后端会等待） */
  const fileIds = computed(() =>
    items.value.filter((a) => a.file && a.status !== 'failed').map((a) => a.file!.file_id),
  )
  const hasFiles = computed(() => fileIds.value.length > 0)

  function apply(f: FileOut) {
    const a = items.value.find((x) => x.file?.file_id === f.file_id)
    if (!a) return
    a.file = f
    a.status = f.parse_status
    a.error = f.parse_error
  }

  async function upload(a: Attachment, file: File) {
    try {
      const cid = await getConversationId()
      a.abort = new AbortController()
      const f = await api.uploadFile(cid, file, (p) => (a.progress = p), a.abort.signal)
      a.file = f
      a.status = f.parse_status
      a.error = f.parse_error
    } catch (e) {
      a.status = 'upload_failed'
      a.error = e instanceof Error ? e.message : '上传失败'
    }
  }

  function add(list: FileList | File[] | null | undefined) {
    const files = Array.from(list || [])
    if (!files.length) return
    const room = MAX_FILES - items.value.filter((a) => a.status !== 'upload_failed').length
    if (room <= 0) {
      toast.push(`一条消息最多附带 ${MAX_FILES} 个文件`, 'error')
      return
    }
    if (files.length > room) toast.push(`一条消息最多附带 ${MAX_FILES} 个文件，多出的已忽略`, 'error')
    for (const file of files.slice(0, room)) {
      const ext = extOf(file.name)
      if (!ALLOWED_EXT.has(ext)) {
        toast.push(`不支持 .${ext || '?'} 文件：${file.name}`, 'error')
        continue
      }
      if (file.size > MAX_FILE_MB * 1024 * 1024) {
        toast.push(`${file.name} 超过 ${MAX_FILE_MB}MB`, 'error')
        continue
      }
      if (!file.size) {
        toast.push(`${file.name} 是空文件`, 'error')
        continue
      }
      const a: Attachment = {
        key: `att-${++seq}`, name: file.name, ext, size: file.size, status: 'uploading', progress: 0, error: null, file: null,
      }
      items.value.push(a)
      // push 后取响应式代理再上传，进度才能刷新界面
      void upload(items.value[items.value.length - 1], file)
    }
  }

  async function remove(key: string) {
    const a = items.value.find((x) => x.key === key)
    if (!a) return
    items.value = items.value.filter((x) => x.key !== key)
    if (a.status === 'uploading') a.abort?.abort()
    if (a.file) {
      try {
        await api.deleteFile(a.file.file_id)
      } catch {
        /* 已发送或已删除：忽略 */
      }
    }
  }

  async function retry(key: string) {
    const a = items.value.find((x) => x.key === key)
    if (!a?.file) return
    try {
      apply(await api.reparseFile(a.file.file_id))
    } catch (e) {
      toast.error(e, '重新解析失败')
    }
  }

  /** 发送后清空（文件已绑定到消息，不删除） */
  function clear() {
    items.value = []
  }

  return { items, uploading, fileIds, hasFiles, add, remove, retry, apply, clear }
}
