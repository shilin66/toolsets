NOC 工作台：Vue 3 + Naive UI
============================

运行方式
--------

继续使用原有 Flask 服务。页面、前端 JS/CSS 和 /api 接口由同一地址及端口提供。
无需新增 Node 服务或前端开发服务器；浏览器不依赖外部 CDN。
后端启动方式和业务接口保持原样。更新代码后重启原服务并刷新管理台，
页面按静态文件修改时间为应用脚本、Vue 和 Naive UI 注入缓存版本号。

设计与组件边界
--------------

桌面工作台仅面向 1280px 及以上宽度。采用深墨绿色导航、低饱和绿色主色、
统一表格/筛选/表单/弹窗，收起导航时保留图标，分页固定在可见工作区。
保留原有业务处理、API payload、确认步骤、三语言和浏览器路由。

* admin-naive.js：主题、布局、菜单、通知、确认框和加载状态。
* admin-naive-controls.js：表单控件，保留数值/布尔选择、日期字符串、
  手动文件上传及表单校验约定。
* admin-naive-display.js：原生 Naive 表格、Tabs、分页、详情、弹层。
* admin-views.js / admin-discovery.js：业务模板通过 ui-* 应用接口使用上述控件。
* admin.css：业务布局和 Naive DOM 的必要样式；根节点 CSS 变量是配色的唯一来源，
  admin-naive.js 在初始化时读取这些变量，供 Naive UI 的主题配置使用。

ui-* 是应用层组件，不是完整的 Element Plus 兼容库；只支持业务已使用的接口。
新增页面应优先使用这些现有组件，新增属性需核实其 Naive UI 语义。
Element Plus 组件库、样式和语言包不再被页面加载。
保留独立的 Vue 图标包 element-plus-icons.js，不需要 Element Plus 运行时。

本地依赖
--------

* Vue 3.5.44： https://unpkg.com/vue@3.5.44/dist/vue.global.prod.js
* Naive UI 2.45.3： https://unpkg.com/naive-ui@2.45.3/dist/index.prod.js
* 许可证：static/vendor/vue.LICENSE、static/vendor/naive-ui.LICENSE。

已保存资源的 SHA-256::

   e0a2a0866a8de8887542e24f3c218aad3d907b88f30966068792ba992296dc9f  vue.global.prod.js
   990226fe05d6a6e533279a7ca6dc56c814dd6e41586db2a68de85be8637534f4  naive-ui.js

验证
----

真实 Chromium + 临时 SQLite fixture，覆盖同源静态资源、10 个路由、
供应商创建/编辑、邮箱校验/保存、Excel 上传预览/取消/确认替换、
草稿发布、割接任务重新生成、删除确认/取消/末页回退。
桌面检查含 1280/1440/1920 宽度及 1280×800 /1440×1000 收起/展开导航，
分页位置使用实际 bounding box 断言，避免元素存在但被视口裁切。
另有三语言切换、刷新记忆和 Enter 登录回归。

执行 UI 回归（需已安装项目依赖、Playwright 和 Chromium）::

   python -m unittest tests.ui.test_naive_migration_ui tests.ui.test_supplier_discovery_ui tests.ui.test_cutover_regeneration_ui tests.ui.test_cutover_deletion_ui tests.ui.test_admin_frontend_api

测试中的业务新增/修改/删除针对临时 fixture，不对接真实 RPA 上报。
真实外部 RPA 和邮件发送依赖未在此次界面迁移中执行。


操作与间距规范
--------------

* 表格重复操作使用 ui-action：32px 点击区域、18px 图标、8px 按钮间距，
  label 同时用于无障碍名称和提示，支持键盘焦点与 Escape 收起提示。
* 新增、保存、导入等主要操作保留文字。工具栏和弹窗 footer 使用公共按钮组。
* 列表首尾单元格、标题和分页使用 20px 共同边距；操作列固定宽度并居中。
* 长表单弹窗内容滚动，标题和底部动作保持可见，覆盖 1280×800 桌面。
* tests/ui/test_action_layout_ui.py 用真实 DOM 几何值、键盘动作和截图检查上述规则。

工作台视觉层级
--------------

* 所有业务页面统一去掉内容区独立的大标题和说明区（含综调会话），顶栏保持 56px，
  使用 16px 的 h1 展示当前页名。卡片标题使用 15px，标题栏垂直留白 8px。
  新增、导入、导出等主要操作位于所属卡片标题栏右侧，筛选另起一行；
  操作随业务视图正常挂载/卸载，不再依赖跨组件 Teleport 或公共标题容器。
  邮件详情和供应商编辑不再重复展示内容区面包屑，通过顶部父级入口返回列表；
  内嵌草稿审核保留表单“取消”，返回草稿详情。
* 值班概览只在割接任务列表展示并加载，正常状态约 66px；标签位于上方，数字和辅助说明
  排在同一行。保留指标跳转、刷新和错误反馈，错误或较长翻译可以自然撑高。
  登录和从其他页面返回列表时重新加载。
* 内容使用中性色；绿色表示主要操作与当前导航，警示仍保留语义色。
* 列表标题和总数独立于筛选行；表格距离卡片左右各 20px，单元格首尾内边距 20px、
  垂直留白通常为 12px，割接任务邮件行采用 8px。表头使用轻微底色，常态行统一白底，
  避免强斑马纹干扰阅读。任务列表的标题、筛选和分页区也使用紧凑间距。
* 详情、供应商编辑、系统配置、表单弹窗共用 12px 表面圆角和中性分隔线。
  旧蓝色表单强调统一为主色，危险与警告保留语义色；弹窗标题分隔、浅色底部动作区，
  长内容滚动时标题及按钮保持可见。
* 线路表格按字段分配列宽，编号和备注最多展示两行，悬停或键盘焦点可查看全文，
  Escape 关闭提示。列表内部滚动，分页保持在底部，覆盖侧栏展开和收起。
* 无标签的邮件不保留空标签行；详情元数据合并为一个信息区，清除叠加的卡片外边距。
* 系统配置按用途分组为桌面双列，字段采用顶部标签，避免小表单横跨整页。
* 弹窗自动聚焦不展开自动补全；用户点击或输入时再展开，避免入场动画期间浮层遮挡字段。

本轮使用临时 SQLite 和 Chromium 验证 45 条线路、24 封邮件的密集列表，
宽度为 1280 / 1440 / 1920px；包括列表分页、筛选、键盘提示、弹窗操作和同源加载。
相关回归入口::

   python -m unittest tests.ui.test_action_layout_ui tests.ui.test_naive_migration_ui tests.ui.test_supplier_discovery_ui tests.ui.test_cutover_deletion_ui tests.ui.test_cutover_regeneration_ui tests.ui.test_admin_frontend_api

组件值与取消行为
----------------

* ui-checkbox 将 true-label / false-label 映射到 Naive UI 的 checkedValue /
  uncheckedValue，默认仍使用布尔值。骨干确认项保留“是 / 否”字符串，提示随实际值变化。
* 深色侧栏为收起状态单独配置 itemIconColorCollapsed，避免继承浅色主题的深色图标。
* NocDialog.confirm 的取消按钮、关闭按钮和 Escape 均以 cancel 结束等待；
  正常取消不应报错或让列表操作停留在忙碌状态。maskClosable 为 false 时，
  点击遮罩不会取消仍然打开的确认操作。
* 线路导入替换文件复用首次选择的格式校验，并保留 File 对象；移除文件同时清除预览。
* tests/ui/test_control_contracts_ui.py 在隔离数据中验证关闭弹窗、替换/移除文件、
  邮箱开关与数字端口、日期筛选以及日期时间保存回显。

上报截图展示
------------

* 历史上报记录与上报进度面板共用 ReportScreenshotGallery。
  缩略图区域固定 160px 高，原图使用 contain 完整缩放，卡片展示步骤序号、名称与时间。
  桌面列数随容器宽度调整，不使用原图尺寸撑开表格。
* 点击或键盘 Enter 打开 Naive UI 图片组预览，保留完整图片分辨率及缩放工具，
  左右方向键切换图片，Escape 关闭后焦点返回触发按钮；不可用图片不进入预览序列。
* 区分加载中和截图不可用；离开详情或重新加载记录后，过期请求产生的 Blob URL 立即释放。
* tests/ui/test_report_gallery_ui.py 使用真实 PNG 和隔离上报记录验证横图、长图、
  无截图、桌面侧栏两种状态、预览切换及延迟加载清理。截图证据位于 .qa/report-gallery/。

统一下拉框与日期选择
------------------

* 所有工作台下拉选择使用 ui-select / ui-option，日期选择使用 ui-date-picker，
  共用系统配置的语言选择、重保日期所用 Naive UI 主题。移除综调环境独立的背景、边框与高度覆盖。
* 运营统计周期、环境、状态、排序、明细类型、分页，以及邮箱授权和已收集邮件选择，
  不再使用浏览器原生 select。样本支持搜索，日期保持 YYYY-MM-DD，重保时间仍保留秒。
* 监听邮箱使用可搜索多选，响应容器宽度折叠标签，保持筛选栏单行高度；
  全选保留管理员“全部邮箱（含历史）”范围，清空仍表示零个邮箱，不能变为全局范围。
* 统计查询保留必填及起止日期校验，结束日历禁选早于开始日期的日期。
* tests/ui/test_control_style_ui.py 对比系统配置与筛选控件的计算样式，
  验证 1280 / 1440 / 1920px、展开面板、Escape 关闭及邮箱范围；
  证据保存于 .qa/unified-controls/。相关原有用例覆盖样本切换、权限保存和日期回显。
