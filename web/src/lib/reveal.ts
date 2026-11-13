import type { Directive } from 'vue'

/**
 * v-reveal：元素进入视口时淡入上移（只触发一次）。可传入延迟毫秒：v-reveal="120"
 *
 * 保证内容不会一直不可见：
 * - 挂载时已在视口内或已在视口上方（锚点跳转、刷新后保留的滚动位置）的元素立即显示；
 * - IntersectionObserver 之外再用滚动事件（捕获阶段，任何滚动容器都能收到）兜底检查；
 * - 用户开启“减少动态效果”或浏览器不支持 IntersectionObserver 时直接显示。
 */
const pending = new Set<HTMLElement>()
let observer: IntersectionObserver | null = null
let listening = false
let raf = 0

function show(el: HTMLElement) {
  el.classList.add('is-visible')
  pending.delete(el)
  observer?.unobserve(el)
}

/** 顶部已进入视口底部（或已滚过）的元素都显示 */
function sweep() {
  const vh = window.innerHeight || document.documentElement.clientHeight
  for (const el of pending) {
    if (el.getBoundingClientRect().top < vh) show(el)
  }
}

function onScroll() {
  if (raf) return
  raf = requestAnimationFrame(() => {
    raf = 0
    sweep()
  })
}

function ensureListeners() {
  if (listening) return
  listening = true
  document.addEventListener('scroll', onScroll, { capture: true, passive: true })
  window.addEventListener('resize', onScroll, { passive: true })
}

function getObserver(): IntersectionObserver | null {
  if (typeof IntersectionObserver === 'undefined') return null
  if (!observer) {
    observer = new IntersectionObserver(
      (entries) => {
        for (const e of entries) if (e.isIntersecting) show(e.target as HTMLElement)
      },
      { rootMargin: '0px 0px -4% 0px', threshold: 0 },
    )
  }
  return observer
}

export const vReveal: Directive<HTMLElement, number | undefined> = {
  mounted(el, binding) {
    el.classList.add('reveal')
    if (binding.value) el.style.transitionDelay = `${binding.value}ms`
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    const io = getObserver()
    if (reduce || !io) {
      el.classList.add('is-visible')
      return
    }
    pending.add(el)
    io.observe(el)
    ensureListeners()
    // 布局稳定后检查一次：已在视口内或上方的立即显示
    requestAnimationFrame(sweep)
  },
  unmounted(el) {
    pending.delete(el)
    observer?.unobserve(el)
  },
}
