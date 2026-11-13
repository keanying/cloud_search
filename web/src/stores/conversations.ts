import { defineStore } from 'pinia'
import { api } from '@/api/client'
import type { ConversationOut } from '@/api/types'

export const useConversationsStore = defineStore('conversations', {
  state: () => ({
    items: [] as ConversationOut[],
    nextCursor: null as string | null,
    loaded: false,
    loading: false,
  }),
  actions: {
    async refresh() {
      this.loading = true
      try {
        const res = await api.listConversations(50)
        this.items = res.items
        this.nextCursor = res.next_cursor
        this.loaded = true
      } finally {
        this.loading = false
      }
    },
    async loadMore() {
      if (!this.nextCursor || this.loading) return
      this.loading = true
      try {
        const res = await api.listConversations(50, this.nextCursor)
        const seen = new Set(this.items.map((c) => c.conversation_id))
        this.items.push(...res.items.filter((c) => !seen.has(c.conversation_id)))
        this.nextCursor = res.next_cursor
      } finally {
        this.loading = false
      }
    },
    upsert(c: ConversationOut) {
      const i = this.items.findIndex((x) => x.conversation_id === c.conversation_id)
      if (i >= 0) this.items[i] = c
      else this.items.unshift(c)
      this.items.sort((a, b) => (a.updated_time < b.updated_time ? 1 : -1))
    },
    remove(id: string) {
      this.items = this.items.filter((c) => c.conversation_id !== id)
    },
  },
})
