# 作业要求与可复核证据

本页将课程要求映射到代码、测试和实际产物，便于独立审查。表内实现情况是项目陈述，最终以运行和代码为准，不预设评分结果。

## 课程依据

依据正式课件 `Homework 2.pptx` 第 2–4 页（本地课程目录，未将课件转载至公开仓库），方向为 Mini SE：需求 → 设计 → 代码。评分维度为流程完整性 40%、Agent 协作 30%、可扩展性 20%、文档 10%。提交要求见 [提交清单](提交清单.md)。

## 核验入口

在仓库根目录使用 Python 3.10+：

```sh
python -X utf8 -m mini_se_workflow.verification
```

Windows 可用 `py -3` 代替 `python`。不调用模型，不需要 `.env`。入口运行全部测试与三项离线复现实验；任何子命令非零、报告缺失或关键结果不符合预期都会记录失败并返回非零。其他检查继续执行，保留诊断。

产物在本轮新建的 `outputs/review/<时间-编号>/`：

| 文件 | 内容和预期 |
|---|---|
| `summary.json` | 各检查命令、返回码、耗时、日志位置、总体通过情况 |
| `unittest.log` | 58 项测试的名称、结果和耗时；必须有最终 `OK` |
| `evaluation.json` | `mode=fixture`，六项均符合预期，模型 HTTP 请求为 0；澄清类成功是停下提问，不是生成代码 |
| `comparison.json` | `mode=comparison-fixture`，两方案各 3 个固定任务符合预期，模型请求为 0 |
| `library-audit.json` | 原/修订均通过旧 8 项；原版独立 9/21、修订 21/21；原版失败应保留 |
| `*.log`、`evaluation-runs/`、`comparison-runs/` | 分项输出、完整状态、消息、每版代码与执行反馈 |

[GitHub Actions](https://github.com/Peanora/mini-se-workflow/actions/workflows/tests.yml) 在 Windows/Ubuntu、Python 3.10/3.13 上运行同一入口，并通过 artifacts 保存证据。查看本次提交对应 run，不能将旧提交绿色状态当成本次结果。

也可独立执行各项：

```sh
python -X utf8 -m unittest discover -s tests -v
python -X utf8 -m mini_se_workflow.evaluation
python -X utf8 -m mini_se_workflow.comparison --repeats 1
python -X utf8 -m mini_se_workflow.library_audit
```

## 必须项与评分维度

模块路径均相对仓库根目录；未写包名的实现文件也位于 `mini_se_workflow/`。

| 要求 / 维度 | 实现 | 核验依据 | 边界 |
|---|---|---|---|
| ≥2 个 Agent 完成流程；流程完整性 | `agents.py` 的 `RequirementsAgent`、`DesignAgent`、`CodingAgent`；`workflow.py` 的 `MiniSEWorkflow` | `tests/test_workflow.py::test_real_execution_failure_feedback_repairs_project`；离线待办 7/9 → 9/9；真实待办归档 `examples/todo-model.zip` | 三个职责可共用模型；验收器不是第四个 Agent |
| 消息传递或共享状态；协作 | `models.py` 的 `WorkflowState`，`workflow.py`、`store.py` | `workflow.json` 的需求、设计、`messages`、`events`、`iterations`；同上测试检查阶段输入和失败反馈 | 消息摘要不等同原始 API 全量记录，不展示隐藏推理 |
| 基本顺序执行；可运行 MVP | `workflow.py`、`cli.py`、`web.py` | 离线 CLI/Web；`tests/test_web.py::test_async_run_progress_history_and_zip_download` | 本地服务一次一个任务 |
| 可扩展性 | [Design.md](Design.md#可扩展性)；独立客户端、Agent、契约、Runner、Store | 客户端注入、Runner 注入；`tests/test_comparison.py::test_same_development_suite_overrides_model_authored_tests` | 新节点需补契约、状态转换及测试，并非无代码插件系统 |
| 文档 | [README](README.md)、[Design](Design.md)、[使用说明](使用说明.md)、本页 | 流程图、职责、运行命令、失败证据、限制、提交与演示指引 | 不用自评得分替代课程评审 |

## 推荐项与质量增强

| 项目 | 测试文件及具体测试 / 证据 | 当前状态 |
|---|---|---|
| 条件和循环 | `test_workflow.py`：`test_questions_stop_before_design_and_coding`、`test_repeated_failure_stops_after_two_repairs` | 澄清/验收分支、有预算循环；无并行调度 |
| 可视化 | `static/index.html`；Web 测试检查 API、历史、下载 | 运行观察及人工确认界面；无拖拽编排 |
| 日志状态 | `store.py` 保存每版验收、`workflow.json`；交付报告和 ZIP | 本机 `outputs/` 不提交；公开样例和新运行可复核 |
| 需求编辑/确认 | `test_lifecycle.py`：`test_review_edits_freeze_and_same_run`、`test_invalid_confirmation_is_non_mutating` | 同一运行续跑、深复制冻结；编号覆盖不保证语义正确 |
| 补充需求 | 同上：`test_clarification_continues_original_run` | 真实模型支持；离线待办只支持固定规格 |
| 重试/恢复 | 同上：`test_design_retry_skips_requirements_and_keeps_budget`、`test_validation_retry_reuses_pending_code`、`test_restart_marks_running_interrupted_and_restores` | 跳过已完成阶段；验收中断复用代码；不重置预算 |
| 取消 | 同上：`test_cancel_before_next_agent_then_resume`；`test_runner.py`：`test_cancel_stops_running_validation_process` | 可终止验收进程；远端调用只能等响应或超时后生效 |
| 差异和交付 | `test_reporting.py`：`test_real_revision_diff_and_archive_report` | 真实文件比较；ZIP 含 `_workflow/report.md` |
| 独立评测与失败保留 | `test_evaluation.py`：`test_independent_failure_is_retained_despite_workflow_pass` | 独立用例不回流编码/返工；失败保留在成绩分母 |
| 文件不变断言 | `test_library_audit.py`：`test_file_preservation_assertion_detects_false_error_response` | 字节/SHA256 检查“报错却改了数据” |
| 核验入口可靠性 | `tests/test_verification.py` | 拒绝非零进程、缺失报告、伪造通过数、错误模式标签 |

上述 `test_*.py` 均在 `tests/` 内，一键入口全部执行。

## 证据来源与解释

| 类型 | 原始材料 | 能支持的结论 |
|---|---|---|
| 离线固定响应 | `demo.py`、`fixtures/`；本轮新结果 | 编排、真实执行、返工和评测机制可运行，不代表模型能力 |
| 真实模型个例 | `examples/todo-model.zip`、`text-stats-model.zip` | 当时个例的阶段产物与验收结果，不保证换需求仍通过 |
| 真实独立评测 | `examples/evaluation-real.json`、`evaluation-followup.json`、`evaluation-failures.json`、[说明](examples/评测说明.md) | 首轮 3/6，定向复测 2/3，分别报告 |
| 图书原始与审查修订 | `examples/library-audit/original-workflow.json`、`original/`、`reviewed/`、`results.json` | 原 8/8 不变，业务复核 9/9；新增要求原 0/12、修订 12/12；修订由开发助手直接完成 |
| 单/三 Agent 真实对照 | [预注册方案](examples/单Agent对照方案.md)、`comparison-real.json`、`comparison-real.md`、`comparison-real.zip`（均在 `examples/`） | 12 次完整流程，单 5/6、三 1/6。ZIP 保留失败、实验时实现与套件；无固定随机种子，小样本不证明一般优劣 |

保存 JSON 并不使数据不可伪造。可重新执行本地样例、交叉检查代码/反馈和归档；重新进行真实模型评测需要自行配置密钥，先估算费用，结果可能不同。本轮仓库整理没有追加真实模型请求。

## 限制与后续方向

- 仅支持标准库、本地 JSON 协议、小型单层 Python 项目，不是通用开发平台。
- 没有操作系统级隔离，不宜执行不可信代码；接口错误重试不等于端到端完成保证。
- 需求覆盖检查关注编号与结构，语义仍需人审；需求契约错误和 JSON 截断可能使流程在编码前停止，不能由编码返工修复。
- 独立套件有限，可能遗漏缺陷；单/三 Agent 实验未证明多 Agent 的质量收益。
- 恢复依赖本地状态与进程信息，无多实例分布式锁；旧记录仅可查看/下载。
- 后续优先补需求阶段的有预算格式纠正、输出长度控制和覆盖错误诊断，实施后另做实验，保留已有失败。
