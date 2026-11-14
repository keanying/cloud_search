# UX Pilot 生成提示词

用于在 UX Pilot 中按本目录的设计规范重新生成界面。共 4 组，分别放在“用户端”“管理端”两个页面（画布）中。
所有界面文字使用简体中文；桌面画布 1920×1080（对话页可 1920×1200）。

## 通用风格段（每组提示词开头都带上）

```
Product: 云搜浏览器 (Cloud Search Browser) — a chat-first research assistant. Cloud agents search and read real web pages in a cloud browser and deliver cited answers, reports (Word/PDF/HTML/Markdown) and data tables (Excel/CSV). All UI copy in Simplified Chinese.
Visual style (must follow): warm, human, calm — NOT a flashy AI look. Warm off-white canvas #F3F3EF, white cards #FFFFFF with 24px radius, 1px hairline borders rgba(17,18,20,.08), soft shadow. Ink black #111214 for primary pill buttons, user chat bubbles, the floating top bar and the admin sidebar. Accent green #1F9163 for links/selected/citation numbers. Pastel card fills with dark text of the same hue: mint #D5EEDF/#1D4D36, lilac #E3DEFA/#3B2F74, butter #F6E9AD/#5A4808, sky #D6E8F7/#1D3F61, peach #F9DACB/#6B2D14. No gradients, no glassmorphism, no glow, no purple-tech look. Font: Plus Jakarta Sans + PingFang SC; big bold numbers with tabular figures. Pills/chips fully rounded; lucide-style thin outline icons. Generous whitespace, content max width 1680px, layouts use the full width of large screens.
```

## 第 1 组 · 用户端：首页、登录（页面：用户端）

```
{通用风格段}
Screen 1 — 首页 (home, 1920×1080): soft illustrated background in the lower half (gentle green rolling hills, a few pine trees, two white clouds, warm pale-yellow sun at upper right), canvas above is warm white. Top-right small round icon buttons: 主题, 深浅色, 设置, 应用九宫格, avatar "林". Centered: heading "你好，今天想探索什么？" (44px bold), subtitle "从一个问题开始，让 AI 帮你搜索、整理数据、生成报告". Large white search bar 720×64 with soft shadow: search icon, placeholder "搜索问题，或描述想采集的数据、想要的报告…", right side a pill dropdown "智能模式 ▾" and a black circular send button. Below: 7 round white quick-action buttons with colored outline icons and labels: 搜索问题, 深入研究, 采集数据, 数据+报告, 最近对话, 我的成果, 管理后台. Bottom-left small white card "2026 年 AI 创业方向研究 · 2 分钟前"; bottom-right clock card "18:42 / 11月13日 星期五"; bottom-center pill "向下了解更多 ⌄".
Screen 2 — 首页向下滚动的介绍区: section "三步完成一次调研" with three pastel cards (mint/lilac/sky): 说出需求 → 云端浏览器真实阅读 → 交付带来源的成果; a product mockup showing chat on the left and a live cloud-browser frame on the right; a highlights grid of 6 white cards with pastel icon squares: 8 个智能体分工协作, 真实浏览器，不走搜索 API, 每句话都有来源, 遇到验证码请你接手, 报告和表格直接下载, 支持 OpenAI / DeepSeek / Kimi / 火山 / 通义 / 智谱; footer with the search bar again.
Screen 3 — 登录 (login): split layout. Left 55% warm canvas with headline "把搜索交给云端，把判断留给你" and three slightly rotated stacked pastel preview cards (a cited answer card, a live browser card, an Excel result card). Right: white card form with tabs 登录 / 注册, inputs 用户名, 密码, black pill button "登录", small note "第一个注册的账号自动成为管理员".
```

## 第 2 组 · 用户端：对话工作台（页面：用户端）

```
{通用风格段}
Screen 1 — 对话工作台 (1920×1200), floating near-black top bar (12px from edges, 16px radius): logo "云搜浏览器", centered pill nav 对话(selected, white pill) / 我的成果 / 设置 / 管理后台, right: history icon, moon icon, avatar "林小舟 ▾". Three columns:
LEFT (280px): black pill "＋ 新对话", search "搜索对话", groups 今天 / 最近 7 天 / 更早, items like "2026 年 AI 创业方向研究 · 2 分钟前" (selected = white card), "长三角新能源车企供应商名单 · 30 分钟前 · 执行中" with a pulsing green dot.
CENTER (fluid): title "2026 年 AI 创业方向研究". User message: right-aligned black bubble "帮我研究一下 2026 年有哪些 AI 创业方向值得做…". Assistant (small logo avatar) shows in order: (a) a row of 4 pastel key-number cards: "182 亿美元 · 智能体赛道融资 ①", ">100% · 融资同比增长 ①", "62% · AI 编程渗透率 ⑤", "3+ 年 · 具身智能研发周期 ⑥"; (b) white answer card with H2 "结论摘要" (left color bar), paragraph with small green circular superscript citation numbers, H2 "关键要点" bullet list, a comparison table (赛道/市场热度/进入门槛/变现周期/适合团队), a bar chart "各赛道 2025 年融资额（亿美元）" in soft blue, a butter note "以上数据来自公开报道和机构报告，口径不完全一致"; bottom toolbar 复制 · Word · PDF · HTML · Markdown and a right pill "查看完整报告"; (c) a citation hover popover over citation ① : "36氪 · 权威媒体 · 2025-12-01", title "2025 年 AI 创投报告：智能体赛道融资翻倍", quoted excerpt with a left gray line, links "查看来源详情" "打开原网页 ↗"; (d) sky card "报告已生成 · AI创业方向研究报告 · 机器检查" with black "预览" and format pills Word/PDF/HTML/Markdown each with a colored dot and download icon; (e) white sources card "引用来源 6 · 其中官方/学术/权威媒体 4 个" in two columns with credibility pills (官方 mint, 学术 lilac, 权威媒体 sky); (f) "接着问" with 3 outlined pill questions. Bottom sticky composer (white, 28px radius): "继续补充要求…", colorful round mode buttons 搜索问题 / 深入研究 / 采集数据 / 数据+报告 / 智能, hint "Enter 发送 · Shift+Enter 换行", black round send button.
RIGHT (420px) "本次任务 ✅ 执行结束": three pastel stat tiles 9 搜索 (sky), 12 已读来源 (mint), 138 证据 (lilac); white task card with mint stage timeline (black check circles, dotted connector): 理解需求并规划搜索, 多引擎搜索, 打开网页实读, 抽取证据, 核验引用, 撰写报告; buttons "浏览器记录" (black) "全部来源"; card "最新来源" with pastel letter avatars (财新, GitHub Blog, IT之家, a16z, 机器之心); card "成果" with format pills.
Screen 2 — 同一工作台，任务执行中 + 人工接手: center shows a lilac "执行计划 · 数据+报告 · 已确认" card with 5 numbered steps and pills "最多 6 次搜索" "最多读取 12 个来源"; a mint progress card (left vertical stage list with done/running/pending states; right 2×3 white stat tiles 9 搜索, 42 候选, 8 已读来源, 4 读取受限/失败, 214 证据); a slightly tilted butter card "需要你协助 · Google 要求人机验证，请完成验证后点‘完成’" with countdown pill "4:43" and black button "打开浏览器"; composer shows a red-outlined pill "停止当前轮". The right column becomes the 云端浏览器 panel (wide, ~45%): tabs 云端浏览器 / 来源 / 文件预览, session tabs "会话1 · 人工操作中" "会话2" "会话3"; a butter bar "你正在操作云端浏览器 · AI 已暂停 · 剩余 4:42" with buttons 刷新页面 (ghost), 完成，交还给 AI (black), 跳过; below a live browser viewport with a green focus ring showing a Google verification page with a visible "进行人机身份验证" checkbox widget; under the frame: 当前地址, 页面标题, 正在做什么 "Google 搜索：…", and a note "点击画面后即可操作；密码不会被记录或发送给 AI".
```

## 第 3 组 · 管理端：概览、智能体分工、模型（页面：管理端）

```
{通用风格段}
Admin layout for all screens: left dark sidebar 248px (#111214, 24px radius, 12px from edges): logo "云搜浏览器 / 管理后台"; nav 概览; group 模型: 供应方, 模型, 智能体分工; group 运行: 搜索与浏览器, 任务限额; group 数据: 任务, 调用记录, 用户. Active item = white pill with black text and a small green dot. Bottom: user card "林小舟 · 管理员" with moon toggle, "返回应用", "收起导航". Content: breadcrumb, page title with icon (36px bold), one-line description, actions on the right.
Screen 1 — 概览: top-right segmented 7天 / 14天(selected) / 30天 and a round refresh button. Row 1: big saturated orange card (#E8693C, white text) "近 14 天任务 95 · 累计 412 个任务", pill "2 个进行中", 14 small dark-orange daily bars, bottom split 完成 86% · 失败 8% · 其他 5%; white card "模型调用 8,432 次请求", 输入 token 4123万, 输出 token 392万, green ring "99% 成功率", footer "费用 ¥187.34 · 12 次待核算 · 63 次失败"; four small white stat cards with pastel icon squares: 14 用户, 186 对话, 233 成果文件, 4,821 已读网页. Row 2: "每日任务" stacked bar chart (完成 green, 失败 orange, 其他 light blue) 2/3 width; "各智能体调用次数" horizontal lilac bars (信息抽取 4320, 搜索规划 1490, 报告写作 884, 需求编译 612, 核验 420, 协调 380, 浏览研究 230, 分析 96). Row 3: "按模型" table (deepseek-chat, deepseek-reasoner, kimi-k2-turbo-preview with calls and token in/out); "搜索引擎" status list (DuckDuckGo, Google with yellow "冷却中" pill, 必应, 百度, 搜狗 grayed "未启用", 维基百科（中文）/arXiv 论文/GitHub tagged "垂直"); "最近失败" list with peach "任务" / lilac "调用" tags, title, reason, relative time.
Screen 2 — 智能体分工: lilac tip card with lightbulb (八个智能体各司其职…) and a butter stat card "3 个可用模型 · 管理模型"; Semi-Design-style table, one row per role (默认模型, 需求编译, 协调, 搜索规划, 浏览研究, 信息抽取, 核验, 分析, 报告写作): name + suggestion pill (建议强推理 / 建议快速低价 / 建议长上下文) + monospace key + description; 主模型 select "DeepSeek · DeepSeek V3.2" or "使用默认模型"; 备用模型 multi-select ("不使用" / "1. DeepSeek V3.2"); 温度 and 最大输出 small inputs with placeholder 默认; status pills "● 未保存" (yellow) / "● 用默认" (gray) and a 保存 button per row; top-right "1 项未保存" + black "保存全部".
Screen 3 — 模型: filter bar (供应方 dropdown, search), table with 模型 (display name + monospace id), 供应方, capability tags (工具调用, 强制工具选择, JSON Schema, 视觉), 上下文, 最大输出, 单价（元/百万 token）, 启用 switch, actions 测试/编辑/删除; a right side drawer open titled "测试模型" showing 连通性 ✓, 结构化输出 ✓, 耗时 1.2s, and an info note "该模型不支持强制工具选择，已自动改用提示词输出".
```

## 第 4 组 · 管理端：搜索与浏览器、任务限额、调用记录、用户（页面：管理端）

```
{通用风格段}
Same admin layout (dark left sidebar, active item highlighted per screen).
Screen 1 — 搜索与浏览器: two columns. Left white card "搜索": draggable engine order list (drag handle, black numbered circle, name + monospace key, up/down arrows, black switch): 1 DuckDuckGo, 2 必应, 3 百度, 4 Google, 搜狗 grayed "未启用"; blue pill "已修改（覆盖 config.yaml）" + "恢复默认"; "使用策略" segmented 优先/轮换; "可用的垂直来源" black selected pills (Google, 维基百科（中文）, Wikipedia (EN), 百度百科, 微信公众号文章, GitHub, arXiv 论文); number steppers (− 10 +) "每次搜索取结果数" with yellow outline + "未保存" tag, "被拦截后冷却（秒）600", "无法访问后冷却（秒）300", each with "范围 … · 默认 …". Left card "浏览器与人工接手": switch "允许请用户接手", stepper "等待接手超时（秒）300", note "系统不会尝试绕过验证". Right mint card "引擎检测": query input "故宫博物院 开放时间", black "▶ 开始检测", info line (浏览器：系统 Edge · 代理：未设置); results table (引擎/来源, 结果 pill: 可用 green / 需人机验证 purple / 无法访问 orange-red / 结果无关 yellow / 无结果 gray, 条数, 耗时, 说明); summary "可用 6/10". Right card "部署配置（只读）" listing 服务 / 数据库 / 云端浏览器 groups with masked values and path "D:\cloud_search\config.yaml". Floating black save bar at bottom center "有 1 项修改尚未保存 · 放弃 · 保存修改".
Screen 2 — 任务限额: sky info banner; 3-column grid of white cards, each with title, description, right-side stepper and "范围 · 默认" footer: 每个任务最多读取网页 9 (with "已修改（覆盖 config.yaml）" + 恢复默认), 每个任务最多搜索次数 6, 同时打开网页数 3, 每个任务最多模型调用 60, 研究任务补查轮数 2.
Screen 3 — 调用记录: filter chips for 9 roles, status segmented 全部/成功/失败, search; Semi-style table: 时间, 智能体 (中文名 + key), 模型, 请求, Token 入/出, 耗时, 费用 (¥0.12 or "待核算"), 状态 pill (成功 green / 失败 orange), 任务 ID; pagination "共 1,284 条 · 20 条/页".
Screen 4 — 用户: search; table: 用户 (letter avatar + 昵称 + 用户名), 角色 (管理员 pill), 状态 (正常 / 已停用), 对话数, 任务数, 注册时间, actions (设为管理员 / 停用) and a confirm popover "确定停用 bob？停用后立即退出登录".
```
