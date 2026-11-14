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
      ],
    },
    {
      // 管理后台：独立布局（深色侧边导航），仅管理员
      path: '/admin',
      component: () => import('@/views/admin/AdminLayout.vue'),
      meta: { admin: true },
      children: [
        { path: '', redirect: { name: 'admin-overview' } },
        { path: 'llm', name: 'admin-llm', redirect: { name: 'admin-overview' } },
        { path: 'overview', name: 'admin-overview', component: () => import('@/views/admin/OverviewView.vue') },
        { path: 'providers', name: 'admin-providers', component: () => import('@/views/admin/ProvidersView.vue') },
        { path: 'models', name: 'admin-models', component: () => import('@/views/admin/ModelsView.vue') },
        { path: 'agents', name: 'admin-agents', component: () => import('@/views/admin/AgentsView.vue') },
        { path: 'search', name: 'admin-search', component: () => import('@/views/admin/SearchSettingsView.vue') },
        { path: 'limits', name: 'admin-limits', component: () => import('@/views/admin/LimitsView.vue') },
        { path: 'tasks', name: 'admin-tasks', component: () => import('@/views/admin/TasksView.vue') },
        { path: 'runs', name: 'admin-runs', component: () => import('@/views/admin/RunsView.vue') },
        { path: 'users', name: 'admin-users', component: () => import('@/views/admin/UsersView.vue') },
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
  if (to.matched.some((r) => r.meta.admin) && !auth.user?.is_admin) return { name: 'home' }
  return true
})
