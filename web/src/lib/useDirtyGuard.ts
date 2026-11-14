import { onBeforeUnmount, onMounted, type Ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'

/** 有未保存修改时：离开页面（路由跳转）先确认；关闭/刷新浏览器标签页时由浏览器提示 */
export function useDirtyGuard(dirty: Ref<number> | Ref<boolean>, message = '有修改尚未保存，确定离开吗？') {
  const isDirty = () => (typeof dirty.value === 'number' ? dirty.value > 0 : !!dirty.value)
  onBeforeRouteLeave(() => (isDirty() ? window.confirm(message) : true))
  function onBeforeUnload(e: BeforeUnloadEvent) {
    if (!isDirty()) return
    e.preventDefault()
    e.returnValue = ''
  }
  onMounted(() => window.addEventListener('beforeunload', onBeforeUnload))
  onBeforeUnmount(() => window.removeEventListener('beforeunload', onBeforeUnload))
}
