import type { Directive } from 'vue'

/**
 * v-reveal：元素进入视口时淡入上移（只触发一次）。
 * 用户开启“减少动态效果”或浏览器不支持 IntersectionObserver 时直接显示。
 * 可传入延迟毫秒：v-reveal="120"
 */
let observer: IntersectionObserver | null = null

function getObserver(): IntersectionObserver | null {
  if (typeof IntersectionObserver === 'undefined') return null
  if (!observer) {
    observer = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            e.target.classList.add('is-visible')
            observer?.unobserve(e.target)
          }
        }
      },
      { rootMargin: '0px 0px -8% 0px', threshold: 0.08 },
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
    io.observe(el)
  },
  unmounted(el) {
    observer?.unobserve(el)
  },
}
