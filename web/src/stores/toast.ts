import { defineStore } from 'pinia'

export interface Toast {
  id: number
  kind: 'info' | 'success' | 'error'
  text: string
}

let seq = 0

export const useToastStore = defineStore('toast', {
  state: () => ({ items: [] as Toast[] }),
  actions: {
    push(text: string, kind: Toast['kind'] = 'info', ms = 4000) {
      const id = ++seq
      this.items.push({ id, kind, text })
      setTimeout(() => this.dismiss(id), ms)
    },
    error(e: unknown, fallback = '操作失败') {
      const msg = e instanceof Error && e.message ? e.message : fallback
      this.push(msg, 'error', 6000)
    },
    dismiss(id: number) {
      this.items = this.items.filter((t) => t.id !== id)
    },
  },
})
