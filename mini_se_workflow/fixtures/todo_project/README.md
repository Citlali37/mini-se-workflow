# 待办事项工具

使用 Python 3.10+，无需第三方依赖。在项目目录中启动 `python main.py`，向标准输入传入一个 JSON 请求，程序返回一个 JSON 对象后退出。

PowerShell 示例：

```powershell
'{"action":"add","title":"完成软件工程作业"}' | py -3 main.py
'{"action":"list"}' | py -3 main.py
'{"action":"complete","id":1}' | py -3 main.py
'{"action":"delete","id":1}' | py -3 main.py
```

数据保存到当前目录的 `tasks.json`。每次请求可重新启动进程，任务编号递增且删除后不复用。

操作协议：新增返回 `{"ok":true,"task":{"id":1,"title":"标题","completed":false}}`；查看返回 `{"ok":true,"tasks":[]}`；完成返回更新后的 task；删除返回 deleted_id。

业务错误返回 `{"ok":false,"error":"错误标识"}`：空白或非文本标题为 empty_title，不合法编号为 invalid_id，不存在的编号为 not_found，未知操作为 unknown_action，数据损坏为 storage_error，输入不是 JSON 对象为 invalid_request。
