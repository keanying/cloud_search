import { defineStore } from 'pinia'
import { api, getToken, setToken } from '@/api/client'
import type { TokenOut, UserOut } from '@/api/types'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null as UserOut | null,
    token: getToken(),
  }),
  getters: {
    isAuthed: (s) => !!s.token,
    displayName: (s) => s.user?.display_name || s.user?.username || '',
  },
  actions: {
    applyToken(t: TokenOut) {
      setToken(t.access_token)
      this.token = t.access_token
      this.user = t.user
    },
    async login(username: string, password: string) {
      this.applyToken(await api.login({ username, password }))
    },
    async register(username: string, password: string, displayName?: string) {
      this.applyToken(await api.register({ username, password, display_name: displayName || null }))
    },
    async fetchMe() {
      this.user = await api.me()
      return this.user
    },
    logout() {
      setToken(null)
      this.token = null
      this.user = null
    },
  },
})
