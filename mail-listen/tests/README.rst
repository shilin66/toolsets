自动化测试
==========

测试集中在本目录，按职责分组：

- ``api/``：割接、邮箱、供应商、系统设置、记录查询和会话 API。
- ``cutover/``：割接提示词、上报服务和已保存数据的保留。
- ``mail/``：邮件解析、轮询、过滤、图片转发和发件箱副本。
- ``storage/``：数据库、原始邮件归档和文件迁移。
- ``rpa/``：登录、上报、会话、验证码和反调试异常处理。
- ``scripts/``：邮箱探测和发件箱写入脚本的隔离测试。
- ``ui/``：工作台页面入口、静态控件声明和样式约束。

运行
----

在项目根目录、已安装 ``requirements.txt`` 的 Python 环境中执行：

.. code-block:: bash

   # 全量测试
   API_KEY=test-key python -m unittest discover -s tests -t .

   # 按模块运行
   API_KEY=test-key python -m unittest discover -s tests/api -t .

   # 割接保存与上报回归
   API_KEY=test-key python -m unittest \
     tests.api.test_cutover_fill_api \
     tests.api.test_cutover_task_api \
     tests.cutover.test_cutover_report_service

   # 单条用例
   API_KEY=test-key python -m unittest \
     tests.api.test_cutover_task_api.CutoverTaskApiTest.test_empty_customer_circuits_can_be_saved_but_not_confirmed_or_reported

``-t .`` 将项目根目录设为测试导入起点，避免 ``tests/rpa``、``tests/scripts``
与同名业务包混淆。也可以直接在项目根目录运行 ``python -m unittest discover``。

浏览器测试需要安装 Chromium，并允许绑定本地临时端口：

.. code-block:: bash

   python -m playwright install chromium
   API_KEY=test-key python -m unittest discover -s tests/rpa -t .

自动化用例使用临时数据库、模拟邮箱或 localhost 模拟页面，不需要连接企业内网。
``ui/`` 的用例检查静态声明，并非真实页面端到端测试；真实桌面 UI 验收以 1280px 及以上宽度为准。

手动工具
--------

- ``scripts/create_test_data.py``：向应用数据库写入测试邮件，不属于自动化用例，
  仅在确认目标为测试数据库后手动运行。
- ``scripts/test_sent_folder_append.py``：真实 SMTP/IMAP 联调工具，会发送邮件，
  不属于自动化测试，不要作为常规回归命令执行。

新增自动化用例放到对应分组，文件名使用 ``test_*.py``。
