import { createRouter, createWebHistory } from 'vue-router'
import { getToken } from '@/api/client'
import { useAuthStore } from '@/stores/auth'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue'), meta: { public: true } },
    {
      path: '/',
      component: () => import('@/views/AppLayout.vue'),
      children: [
        // 首页（搜索 + 产品介绍）对未登录访客公开；发起搜索时再引导登录
        { path: '', name: 'home', component: () => import('@/views/HomeView.vue'), meta: { public: true } },
        { path: 'chat/:id', name: 'chat', component: () => import('@/views/ChatView.vue'), props: true },
        { path: 'artifacts', name: 'artifacts', component: () => import('@/views/ArtifactsView.vue') },
        { path: 'settings', name: 'settings', component: () => import('@/views/SettingsView.vue') },
        {
          path: 'admin/llm',
          name: 'admin-llm',
          component: () => import('@/views/AdminLlmView.vue'),
          meta: { admin: true },
        },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (to.meta.public) {
    // 公开页面：已登录则补全用户信息；令牌失效时按未登录处理
    if (getToken() && !auth.user) {
      try {
        await auth.fetchMe()
      } catch {
        auth.logout()
      }
    }
    return true
  }
  if (!getToken()) return { name: 'login', query: { redirect: to.fullPath } }
  if (!auth.user) {
    try {
      await auth.fetchMe()
    } catch {
      return { name: 'login', query: { redirect: to.fullPath } }
    }
  }
  if (to.meta.admin && !auth.user?.is_admin) return { name: 'home' }
  return true
})
