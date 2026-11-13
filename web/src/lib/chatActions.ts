import { inject, type InjectionKey } from 'vue'

export interface ChatActions {
  /** 聚焦底部输入框，可附带提示（如“调整范围”） */
  focusComposer: (hint?: string) => void
}

export const ChatActionsKey: InjectionKey<ChatActions> = Symbol('chat-actions')

export function useChatActions(): ChatActions {
  return inject(ChatActionsKey, { focusComposer: () => {} })
}
