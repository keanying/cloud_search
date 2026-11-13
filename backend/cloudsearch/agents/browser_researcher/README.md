# browser_researcher 浏览研究

**职责**：在云端浏览器中实际打开来源并取得正文。

- 默认路径（程序）：导航 → 等待加载 → 正文抽取（trafilatura）→ 截图更新阅览帧。不调用模型。
- 交互路径（模型）：正文不足时，最多 3 步“观察 → 模型选择一个动作 → 程序执行 → 重新观察”。
  - 动作只有 click / scroll / finish；click 只能使用当前观察签发的 element_id（每次观察重新签发），不接受 CSS/XPath/脚本
  - 登录、注册、购买、下载类元素不进入观察列表；遇到验证码/登录墙标记 blocked，不绕过
- 所有请求（含重定向、子资源）经出口 SSRF 检查；单 context 内动作串行
- 输出：PageRead（captured / no_content / blocked / failed，含最终 URL、标题、页面声明的作者/发布时间）
