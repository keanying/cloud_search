// 本地偏好：主题、首页插画背景、搜索时自动打开浏览器阅览。仅保存在本浏览器。
import { defineStore } from 'pinia'

export type Theme = 'light' | 'dark'
export type HomeArt = 'glass' | 'hills' | 'pond' | 'night' | 'plain'

export const HOME_ARTS: { value: HomeArt; label: string; dark: boolean }[] = [
  { value: 'glass', label: '幻彩', dark: false },
  { value: 'hills', label: '山野', dark: false },
  { value: 'pond', label: '荷塘', dark: false },
  { value: 'night', label: '星夜', dark: true },
  { value: 'plain', label: '简洁', dark: false },
]

function initialTheme(): Theme {
  const saved = localStorage.getItem('cs_theme')
  if (saved === 'light' || saved === 'dark') return saved
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function initialArt(): HomeArt {
  const v = localStorage.getItem('cs_home_art') as HomeArt | null
  return v && HOME_ARTS.some((a) => a.value === v) ? v : 'glass'
}

function applyTheme(t: Theme) {
  document.documentElement.classList.toggle('dark', t === 'dark')
}

export const usePrefsStore = defineStore('prefs', {
  state: () => ({
    theme: initialTheme(),
    /** 用户是否通过主题开关明确选择了深色（选择浅色插画时不覆盖） */
    explicitDark: localStorage.getItem('cs_theme_explicit') === 'dark',
    homeArt: initialArt(),
    autoOpenBrowser: localStorage.getItem('cs_auto_open_browser') !== '0',
  }),
  actions: {
    init() {
      applyTheme(this.theme)
    },
    setTheme(t: Theme, explicit = true) {
      this.theme = t
      localStorage.setItem('cs_theme', t)
      if (explicit) {
        this.explicitDark = t === 'dark'
        localStorage.setItem('cs_theme_explicit', t)
      }
      applyTheme(t)
    },
    toggleTheme() {
      this.setTheme(this.theme === 'dark' ? 'light' : 'dark')
    },
    /** 选择首页插画：星夜切换为深色；其他插画切换为浅色，除非用户明确选择过深色 */
    setHomeArt(a: HomeArt) {
      this.homeArt = a
      localStorage.setItem('cs_home_art', a)
      const art = HOME_ARTS.find((x) => x.value === a)
      if (art?.dark) this.setTheme('dark', false)
      else if (!this.explicitDark) this.setTheme('light', false)
    },
    setAutoOpenBrowser(v: boolean) {
      this.autoOpenBrowser = v
      localStorage.setItem('cs_auto_open_browser', v ? '1' : '0')
    },
  },
})
