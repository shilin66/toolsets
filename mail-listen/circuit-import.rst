线路增量导入与模板下载
======================

目标与范围
----------
桌面工作台（1280px 起）默认增量导入，仅新增；全量覆盖保留独立入口和二次确认。
按 Supplier 和换行分隔后的完整 Supplier Circuit ID 去重，保留大小写、前导零和标点。
系统已存在、编号部分重合及文件内冲突整行跳过，文件内完全重复只处理第一行。
缺少必填值或非法 Excel 单元格阻止整批写入；Circuit ID 值可空。
模板保留六列表头，默认空白“线路表”页与独立“填写说明与示例”页。
不创建或修改 Git 提交、分支，不连接真实邮箱或更改现有线路台账。

接口契约
--------
POST /api/circuits/import 的 mode=append 为增量；省略 mode 保留旧版全量语义。
预览返回全部行的原始行号、处理状态、原因、数量及限时 preview_token。
确认上传同一文件并携带 confirm=true、preview_token；事务内重新分类和比对。
发生变化返回 409 及新预览，校验错误返回 400，均不写入。
成功返回 inserted/skipped/error 数量和结果 Excel 的 base64 内容（无需持久化上传文件）。
GET /api/circuits/template 返回模板，使用现有共享配置登录权限。
上传上限 10 MiB、10,000 个数据行；压缩包解压大小、工作表行列和单元格长度另有限制。

实现位置与约定
--------------
supplier_circuits.py 复用字段和表头；circuit_import.py 负责增量分类、事务、模板及报告。
api_server.py 接口仅编排输入输出，沿用 success/message/data 和 snake_case 字段。
static/admin-circuit-import.js 管理导入状态；static/admin-views.js 使用现有 ui-* 组件，文案覆盖三种语言。
不添加依赖或改变数据库结构。

验证
----
API_KEY=test-key MAIL_DATABASE_PATH=/tmp/mail-listen-circuit-test.db python -m unittest tests.api.test_supplier_circuits_api tests.api.test_circuit_incremental_api
API_KEY=test-key MAIL_DATABASE_PATH=/tmp/mail-listen-circuit-ui.db python -m unittest tests.ui.test_circuit_import_ui tests.ui.test_control_contracts_ui
node --check static/admin-views.js

验收包括：预览不写入、已有数据不变、全量兼容、空值错误、文件冲突、多值重合、
重复提交、并发提交、预览失效、事务回滚、模板前导零/多行/无示例误导入，
以及 1280/1440px 下上传、筛选、结果下载、模板下载和全量二次确认。
