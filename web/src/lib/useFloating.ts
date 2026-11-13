import { nextTick, onBeforeUnmount, ref, watch, type Ref } from 'vue'

/**
 * 弹出菜单定位：菜单通过 <Teleport to="body"> 渲染在页面顶层，并按触发按钮在屏幕上的位置用 fixed 定位。
 * 这样不会被后面的毛玻璃卡片（backdrop-filter 会形成独立层叠上下文）遮挡，也不会被滚动区域裁切。
 *
 * placement：'bottom-start' 在按钮下方左对齐；'top-start' 上方左对齐；'top-end' 上方右对齐。
 * 空间不足时自动翻转到另一侧，并限制在视口内。
 */
export type Placement = 'bottom-start' | 'top-start' | 'top-end'

export function useFloating(
  anchor: Ref<HTMLElement | null>,
  menu: Ref<HTMLElement | null>,
  open: Ref<boolean>,
  placement: () => Placement,
) {
  const style = ref<Record<string, string>>({ position: 'fixed', top: '0px', left: '0px', visibility: 'hidden' })
  const GAP = 8
  const MARGIN = 8

  function update() {
    const a = anchor.value
    const m = menu.value
    if (!a || !m) return
    const r = a.getBoundingClientRect()
    const w = m.offsetWidth
    const h = m.offsetHeight
    const vw = window.innerWidth
    const vh = window.innerHeight
    const p = placement()
    let wantTop = p.startsWith('top')
    // 空间不足则翻转
    if (wantTop && r.top - GAP - h < MARGIN && r.bottom + GAP + h <= vh - MARGIN) wantTop = false
    if (!wantTop && r.bottom + GAP + h > vh - MARGIN && r.top - GAP - h >= MARGIN) wantTop = true
    const top = wantTop ? r.top - GAP - h : r.bottom + GAP
    let left = p.endsWith('end') ? r.right - w : r.left
    left = Math.min(Math.max(left, MARGIN), vw - w - MARGIN)
    style.value = {
      position: 'fixed',
      top: `${Math.max(MARGIN, Math.min(top, vh - h - MARGIN))}px`,
      left: `${left}px`,
      visibility: 'visible',
    }
  }

  function onDocDown(e: MouseEvent) {
    const t = e.target as Node
    if (anchor.value?.contains(t) || menu.value?.contains(t)) return
    open.value = false
  }
  function onKey(e: KeyboardEvent) {
    if (e.key === 'Escape') open.value = false
  }

  function bind() {
    document.addEventListener('mousedown', onDocDown)
    document.addEventListener('keydown', onKey)
    window.addEventListener('resize', update)
    window.addEventListener('scroll', update, true) // 捕获阶段：任意滚动容器滚动都重新定位
  }
  function unbind() {
    document.removeEventListener('mousedown', onDocDown)
    document.removeEventListener('keydown', onKey)
    window.removeEventListener('resize', update)
    window.removeEventListener('scroll', update, true)
  }

  watch(open, async (v) => {
    if (v) {
      style.value = { ...style.value, visibility: 'hidden' }
      await nextTick()
      update()
      bind()
    } else {
      unbind()
    }
  })
  onBeforeUnmount(unbind)

  return { style, update }
}
