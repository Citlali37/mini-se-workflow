# Mini SE 工作流

输入软件需求，由需求、设计、编码三个 Agent 协作生成小型 Python 项目。系统实际运行验收用例，把失败输入、实际输出和错误返回编码 Agent，默认最多返工两次（可配置0–5次）。最终项目、每版代码和验收记录都可查看。

```text
用户需求 → 需求 Agent → 设计 Agent → 编码 Agent → 实际验收
                                            ↑          │
                                            └─ 未通过 ─┘（最多返工2次）
                                                       │
                                                    全部通过
                                                       ↓
                                                   下载项目
```

## 功能

- 三个独立职责的 Agent，共享结构化需求、设计、代码与运行状态。
- 编码前固定验收用例；需求编号在设计和用例中可追踪。
- 实际启动生成的程序，检查语法、JSON 输出、业务行为与进程重启后的持久化。
- 失败反馈驱动返工；达到上限仍不通过时明确显示未通过状态。
- 本地 Web 界面展示需求、设计、各版代码、测试结果、消息传递和执行日志。
- 保存运行历史，支持项目 ZIP 下载及命令行使用。
- 无密钥离线演示。离线响应使用固定模板，验收执行真实运行 Python 程序。
- 待办事项示例额外使用四个固定测试用例，覆盖多任务持久化、空白标题、非法编号等行为。

## 环境与启动

Python 3.10 或更高版本。运行时无需第三方 Python 包。

### 先体验离线演示

双击 `启动离线演示.bat`，浏览器会打开 **http://127.0.0.1:8002**。点击“开始开发”，检查需求与验收条件并点击“确认并继续开发”，观察第一次验收失败、编码 Agent 返工以及复验通过。

也可以在本项目目录运行：

```powershell
py -3 -X utf8 -m mini_se_workflow --demo --web --open-browser
```

离线模式仅支持页面预置的待办事项需求。首稿故意遗漏标题校验，第一次实际验收应通过7/9个用例，返工后通过9/9。离线响应不会分析自由需求，也不代表真实模型的生成能力。

### 使用 DeepSeek 处理自由需求

```powershell
Copy-Item .env.example .env
```

在 `.env` 中填写自己的 `DEEPSEEK_API_KEY`，然后双击 `启动Web界面.bat`。也可运行：

```powershell
py -3 -X utf8 -m mini_se_workflow --web --open-browser
```

可配置模型、接口地址、超时与重试次数。环境变量优先于本地 `.env`。`.env` 已被 Git 忽略，项目下载不会包含密钥。

页面“填入示例”会同时开启固定的待办事项验收。如果修改示例文字，将作为自定义需求运行，使用需求 Agent 生成的验收用例。超出范围或存在核心歧义时，需求 Agent 可返回待确认问题，流程暂停在需求阶段；在页面填写答案后继续原任务，运行编号不变。需求明确后先检查、编辑并确认规格，再进入设计。

### 命令行

```powershell
# 不需要密钥，实际执行完整演示
py -3 -X utf8 -m mini_se_workflow --demo --example todo

# 使用模型处理文本统计需求
py -3 -X utf8 -m mini_se_workflow --task-file examples/text-stats-requirement.txt

# 导出 ZIP，请选择尚不存在的目标文件
py -3 -X utf8 -m mini_se_workflow --demo --example todo --export outputs/todo-demo.zip

# 不允许返工，展示首次验收失败的情况
py -3 -X utf8 -m mini_se_workflow --demo --max-repairs 0
```

返回码：`0` 为验收通过，`2` 为需要补充需求或验收未通过，`1` 为运行异常。

## 生成项目的协议

首版支持使用标准库的小型本地 Python 工具，最多10个根目录文件，必须包含 `main.py` 和 `README.md`。

每次执行 `python main.py`，从标准输入读取一个 JSON 对象，在标准输出返回一个 JSON 对象并以0退出；业务错误通过 JSON 表达。程序不应输出交互提示或额外日志到标准输出。

```json
{"action":"add","title":"完成作业"}
```

对应示例输出：

```json
{"ok":true,"task":{"id":1,"title":"完成作业","completed":false}}
```

同一用例每个步骤重启进程、共享工作目录，因此能够验证本地文件持久化。不同用例使用独立的临时目录。验收预期采用对象字段递归包含比较；数组长度及顺序精确比较，布尔值与数字区分。未指定的对象字段允许存在。

## 输出与示例

运行记录默认保存在 `outputs/<运行编号>/`：

```text
workflow.json                 完整共享状态、消息及日志
revision-0/project/           初稿完整项目
revision-0/validation.json    初稿验收结果
revision-1/project/           第一次返工项目（发生返工时）
revision-1/validation.json    复验结果
```

ZIP 包含最终项目文件，以及 `_workflow/` 下的需求规格、设计和完整流程记录。未通过的项目也可以下载，但页面会明确保留“验收未通过”状态；生成文件不等同于验收通过。

`examples/todo-demo.zip` 是已实际验证的离线示例产物；`examples/text-stats-model.zip` 是真实 DeepSeek 生成的文本统计项目，包含完整开发记录，该次运行7/7个验收用例通过。另外六个独立检查记录在 `examples/text-stats-independent-checks.json`，用于补查 Unicode 换行、混合文本、布尔值与数组等输入。这些是本次示例的结果，后续生成结果需重新验收。

`examples/todo-model.zip` 是真实模型生成的待办事项项目：第一次编码文件清单不符，第一次返工后源码范围检查未通过，第二次返工后13/13个用例通过。记录展示了模型真实收到反馈并修改代码的过程。

`examples/todo-requirement.txt` 与 `examples/text-stats-requirement.txt` 是示例需求。录制演示可参考 `演示说明.md`。

## 测试

```powershell
py -3 -X utf8 -m unittest discover -s tests -v
```

测试覆盖真实进程执行、失败返工、验收冻结、返工上限、需求澄清、故障状态保存、文件路径约束、超时、输出限制、进程环境、模型接口错误，以及 Web 运行历史和 ZIP 下载。

## 项目结构

| 模块 | 职责 |
|---|---|
| `agents.py` | 三个 Agent 的提示词及输入输出 |
| `contracts.py` | 需求、设计、代码的数据校验与需求追踪 |
| `workflow.py` | 顺序编排、返工循环和共享状态 |
| `runner.py` | 源码检查、真实进程执行与预期比较 |
| `store.py` | 保存运行记录、版本产物与项目打包 |
| `llm.py` | DeepSeek JSON 模型接口与有限重试 |
| `demo.py` | 离线响应和独立固定验收用例 |
| `web.py`、`static/index.html` | 本地 Web API 与页面 |

架构与扩展方式见 `Design.md`。

## 执行范围与限制

- 生成程序会在本机运行。临时目录、精简环境、导入检查、超时和输出限制用于减少错误影响，**不是操作系统级沙箱**。导入检查无法防御恶意 Python 代码，也不阻止全部文件访问。不要使用不可信模型生成的代码；若处理不可信输入，需增加容器或系统级隔离。
- 不支持网络、第三方包安装、系统命令、子进程及复杂目录。存储使用当前工作目录中的相对路径。
- 默认每步最多5秒，每轮验收总预算60秒，合计标准输出与错误输出限制64 KB。
- 真实模型生成的验收用例也可能有遗漏或错误。固定示例测试能补充特定功能检查，不能证明所有程序都正确。需求正确性仍需人工核对。
- 单次运行是串行流程，本地服务一次只运行一个任务。服务关闭后，未完成任务标为中断；可以查看历史记录并显式从检查点恢复，不自动消耗模型费用。
- 返工预算耗尽时保留最后一份有效文件及全部反馈；模型或执行器异常可重试失败节点，恢复不重置返工预算。


## 升级版：需求确认与恢复

Web 默认在需求分析后暂停。编辑表单可修改需求说明、假设和验收输入输出；完整规格编辑可新增或删除需求与用例，保存前检查编号关联和覆盖。点击“确认并继续开发”后冻结验收条件。离线模板只支持确认原规格，不能演示自由规格修改。真实模型模式支持编辑及补充需求，所有修改记录留在原运行中。

运行失败、服务中断或取消后，在历史记录中选择对应任务，点击“从检查点恢复”。已完成的需求/设计不重复调用；代码已生成但验收中断时复用该版代码重新验收。取消可中止验收子进程；等待模型响应时只能在响应返回或超时后取消，不能撤回已经发出的远端请求。不要同时启动多个服务操作同一输出目录；进程存活检查避免把另一进程运行中的任务误标为中断，但不提供分布式锁。

CLI 保留默认自动执行，也可分阶段：

```powershell
py -3 -X utf8 -m mini_se_workflow --demo --review
# 替换下面的编号为上一步输出的真实运行编号
py -3 -X utf8 -m mini_se_workflow --demo --resume <运行编号> --action confirm
# 真实模型模式，规格文件可取自 workflow.json 的 specification 字段
py -3 -X utf8 -m mini_se_workflow --resume <运行编号> --action confirm --spec-file specification.json
py -3 -X utf8 -m mini_se_workflow --resume <运行编号> --action clarify --answer "需要保存在本地文件"
py -3 -X utf8 -m mini_se_workflow --resume <运行编号> --action retry
```

旧版记录可查看和下载，但没有恢复检查点，不能续跑。新任务可用 `--max-repairs 0` 到 `--max-repairs 5` 配置预算，默认2。初稿不计返工，所以默认最多产生3版；这不是课程限制，也不是模型只能修两次。有限预算控制时间、费用和重复失败，耗尽后需要检查需求或设计，再新建任务。

## 代码差异、报告与评测

代码面板可查看每版实际文件差异和失败原因。“下载交付报告”导出 Markdown，项目 ZIP 中也包含 `_workflow/report.md`。报告记录需求确认、需求→文件→用例追踪、各版通过情况和差异；不把编号关联当成语义正确性证明。

```powershell
# 无密钥离线机制验证
py -3 -X utf8 -m mini_se_workflow.evaluation
# 会产生费用，先按 examples/评测说明.md 的方法估算；费用配置可能变化
py -3 -X utf8 -m mini_se_workflow.evaluation --real --output outputs/evaluation-real.json
```

六项评测覆盖正常、边界、歧义和超范围。独立用例预先固定，不发给编码 Agent，也不作为返工反馈；报告保存失败输入输出和套件哈希。离线固定响应只能验证机制。首轮真实结果、定向复测及费用说明见 `examples/评测说明.md`，不能把两次实验拼成六项全通过的成绩。

GitHub Actions 在 push/PR 时测试 Windows/Linux、Python 3.10/3.13，不使用真实模型密钥。升级要求、进展、验收依据和已知限制集中记录在 `项目进展.md`。
