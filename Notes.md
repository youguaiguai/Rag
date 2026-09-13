# Modular RAG MCP Server 学习笔记

---

## 一、`.github/skills/` 目录下 9 个 Skill 功能与作用

### 开发阶段用到的 Skill（核心 3 个）

#### 1. `auto-coder` — 自动编码引擎 ⭐⭐⭐

**功能**：读取 DEV_SPEC → 找到下一个待做任务 → 实现代码 → 跑测试 → 记录进度

| 组成 | 作用 |
|-----|------|
| `SKILL.md` | 定义 5 步流水线：Sync Spec → Find Task → Implement → Test → Persist |
| `references/01~07.md` | 从 DEV_SPEC.md 同步出来的章节参考，AI 编码时按需读取 |
| `scripts/sync_spec.py` | 将 DEV_SPEC.md 拆分为 7 个 reference 文件，保持同步 |

**触发方式**：对 AI 说 `auto code`、`自动开发`、`auto code B2`（指定任务编号）

**核心流程**：
```
Sync Spec(同步规格) → Find Task(找未完成任务) → Implement(编码) 
→ Test(测试，最多3轮自动修复) → Persist(更新DEV_SPEC进度 + 可选commit)
```

**7 个参考文件说明**：

| 文件 | 内容 | 何时读取 |
|------|------|---------|
| `01-overview.md` | 项目概述与目标 | 首次任务或需要项目上下文时 |
| `02-features.md` | 功能规格说明 | 实现功能相关任务时 |
| `03-tech-stack.md` | 技术栈与依赖选型 | 选择库或模式时 |
| `04-testing.md` | 测试约定与策略 | 编写测试时 |
| `05-architecture.md` | 架构与模块设计 | 创建/修改模块时 |
| `06-schedule.md` | 任务排期与状态 | 每个周期（Sync Spec 步骤） |
| `07-future.md` | 未来路线图 | 规划或评估范围时 |

**任务状态标记**：`[ ]` 未开始 | `[~]` 进行中 | `[x]` 已完成

---

#### 2. `setup` — 一键环境配置 ⭐⭐

**功能**：交互式向导，引导你选 Provider → 配 API Key → 安装依赖 → 生成 settings.yaml → 启动 Dashboard

| 组成 | 作用 |
|-----|------|
| `SKILL.md` | 7 步流水线：Preflight → Ask → Generate Config → Install → Validate → Launch → Guide |
| `references/settings_template.yaml` | 配置文件模板 |
| `references/provider_profiles.md` | 各 Provider 的字段、模型、维度对照表 |
| `references/new_provider_guide.md` | 如何脚手架新 Provider（如 Qwen/Gemini） |

**触发方式**：对 AI 说 `setup`、`环境配置`、`初始化`

**7 步流程详解**：
1. **Preflight**：检查 Python 版本(≥3.10)、创建/激活 .venv
2. **Ask User**：批量询问（4个一批）— LLM Provider / Embedding Provider / Vision 开关 / Rerank 模式
3. **Scaffold**（如需要）：如果选了未内置的 Provider（如 Qwen/Gemini），自动脚手架实现代码
4. **Generate Config**：基于模板+用户回答生成 `config/settings.yaml`
5. **Install Deps**：`pip install -e ".[dev]"` + 特定依赖
6. **Validate**：验证配置能正确加载，失败则自动修复（≤3轮）
7. **Launch + Guide**：启动 Dashboard 并展示快速上手指南

**内置 Provider**：OpenAI、Azure、DeepSeek、Ollama。选其他 Provider 时会自动脚手架代码。

---

#### 3. `qa-tester` — 自动化 QA 测试 ⭐⭐

**功能**：读取 QA_TEST_PLAN.md，逐条执行所有类型的测试（CLI / Dashboard UI / MCP 协议），自动修复失败，记录结果

| 组成 | 作用 |
|-----|------|
| `SKILL.md` | 严格串行的 5 步流水线：Pick → Set State → Execute → Fix → Record |
| `QA_TEST_PLAN.md` | 完整测试计划（A~O 共 15 个 Section） |
| `QA_TEST_PROGRESS.md` | 测试执行进度记录 |
| `references/test_patterns.md` | AppTest / MCP JSON-RPC 的测试代码模板 |
| `scripts/qa_bootstrap.py` | 测试环境初始化/清理/状态检查 |
| `scripts/qa_config.py` | Provider 配置切换/恢复 |
| `scripts/qa_multistep.py` | 多步骤测试执行器 |
| `scripts/qa_validate_notes.py` | 测试记录格式校验 |

**触发方式**：对 AI 说 `run QA`、`QA 测试`、`跑测试`、`run QA G`（指定 Section）

**5 条铁律**：
1. **严格串行**：一次只跑一个测试，记录完再选下一个
2. **Pass = 终端输出证据**：必须在本 session 实际运行并看到输出
3. **零交叉引用**：每条测试独立验证，不能写"同上"
4. **零推断**：不能通过读代码推断通过，必须实际运行
5. **对抗思维**：找 Bug 而不是确认

**测试类型与执行方式**：

| Sections | 类型 | 执行方式 |
|----------|------|---------|
| A–F | Dashboard UI | AppTest headless 渲染 |
| G, H, I | CLI | 终端命令，检查 exit code + stdout |
| J | MCP 协议 | JSON-RPC subprocess |
| K, L | Provider 切换 | qa_config.py apply → 运行 CLI/Dashboard |
| M | 配置与容错 | 修改 settings → 运行 CLI → 验证错误处理 |
| N, O | 数据生命周期 | qa_multistep.py 多步骤执行 |

---

### 项目交付阶段用到的 Skill

#### 4. `package` — 清理打包

**功能**：删除 `__pycache__`、`.venv`、缓存、日志，脱敏 API Key，产出干净可分发的代码包

| 组成 | 作用 |
|-----|------|
| `SKILL.md` | 4 步：Dry-run → Confirm → Execute → Verify |
| `scripts/clean.py` | 实际执行清理的脚本 |

**触发方式**：对 AI 说 `package`、`清理项目`、`打包`

**清理内容**：
- Python 缓存：`__pycache__/`、`.pytest_cache/`、`.mypy_cache/`
- 虚拟环境：`.venv/`
- 构建产物：`build/`、`dist/`、`*.egg-info/`
- IDE 文件：`.idea/`、`.vscode/`
- 数据与日志：`data/`、`logs/`、`cache/`（可用 `--keep-data` 保留）
- 密钥脱敏：`config/settings.yaml` 中的 api_key → `"YOUR_API_KEY_HERE"`

---

### 面试求职阶段用到的 Skill（4 个）

#### 5. `resume-writer` — 简历生成器

**功能**：基于"写作原则 + 项目亮点 + 用户画像 = 定制化简历"三角模型，生成四段式简历项目经历

| 组成 | 作用 |
|-----|------|
| `SKILL.md` | 5 阶段：加载知识 → 画像采集 → 内容生成 → 输出格式 → 迭代+面试追问预测 |
| `references/resume_principles.md` | 简历写作原则（四段式结构、技术标签、亮点挖掘、常见误区） |
| `references/project_highlights.md` | 10 大技术亮点（含话术方向和量化角度） |

**触发方式**：对 AI 说 `写简历`、`resume`

**5 阶段流程**：
1. **加载知识**：读取写作原则 + 项目亮点
2. **画像采集**（4 个问题）：目标岗位 / 业务背景 / 技术侧重(多选) / 特殊要求
3. **内容生成**：亮点匹配 → 四段式输出（背景→目标→过程→结果）
4. **输出格式**：严格四段式，每条 bullet 动词开头+三段式+量化
5. **迭代+追问预测**：根据反馈调整 + 提供 3~5 条面试追问预测

**放大策略底线**：不声称使用了未实现的技术，不声称完成了"未来扩展"的功能。

---

#### 6. `interview-prep` — 模拟面试官

**功能**：5 种面试官风格，3 方向追问，掷骰选题保证每次不同，生成面试报告

| 组成 | 作用 |
|-----|------|
| `SKILL.md` | 完整面试流程：选风格 → 掷骰选题 → 三方向面试 → 生成报告 |
| `references/project_knowledge.md` | 各模块技术要点与评估标准 |
| `references/question_bank.md` | 三方向完整题库 |
| `references/report_template.md` | 面试报告模板+参考答案+评分细则 |

**触发方式**：对 AI 说 `模拟面试`、`面试练习`

**5 种面试官风格**：

| 风格 | 代号 | 特点 |
|------|------|------|
| 速攻广度型 | `FAST` | 快速过完所有模块，不追问，考广度 |
| 深挖发散型 | `DEEP` | 从回答延伸追问，形成发散式对话 |
| 源码拷问型 | `CODE` | 精确到代码级别，不接受"大概是" |
| 压力质疑型 | `HARD` | 无论答好答坏都追问挑战 |
| 随机混搭型 | `MIX` | 每题随机切换风格 |

**三方向面试**：
1. **项目综述**：开场题池 12 道，掷骰选取
2. **简历深挖**（包装识别）：P1量化指标/P2强动词/P3技术词汇，掷骰选题池
3. **技术深挖**：A~G 七组共 55 道，掷骰选主题组

---

#### 7. `project-learner` — 项目学习教练

**功能**：10 大知识域 × 45 个知识点，面试式问答，即时评分，持久化学习进度

| 组成 | 作用 |
|-----|------|
| `SKILL.md` | 9 阶段：发现项目 → 检查历史 → 用户意图 → 选知识点 → 生成问题 → 互动问答 → 评估 → 学习指南 → 持久化 |
| `references/LEARNING_PROGRESS.md` | 学习进度追踪（45 知识点） |

**触发方式**：对 AI 说 `学习项目`、`了解项目`

**10 大知识域**：

| ID | 知识域 | 知识点数 |
|----|--------|---------|
| D1 | RAG Pipeline 整体架构 | 5 |
| D2 | Ingestion Pipeline | 5 |
| D3 | Hybrid Search & Retrieval | 5 |
| D4 | Rerank 机制 | 4 |
| D5 | MCP Server 协议 | 4 |
| D6 | 可插拔架构 & 配置系统 | 5 |
| D7 | 多模态处理 | 4 |
| D8 | 可观测性 & 评估体系 | 5 |
| D9 | 测试策略 & 工程化 | 4 |
| D10 | Document Manager & 幂等性 | 4 |

**评分规则**：4 维度（准确性/深度/代码关联/设计思维）各 10 分，综合取平均。≥7 掌握、4-6 学习中、≤3 薄弱。

---

#### 8. `project-review` — 项目复习老师

**功能**：9 章 71 题，苏格拉底式提问+即时反馈，按章节系统复习，记录掌握进度

| 组成 | 作用 |
|-----|------|
| `SKILL.md` | 授课循环：出题 → 听回答 → 点评+参考答案 → 记录掌握度 |
| `references/question_bank.md` | 9 章共 71 道题目+参考答案 |
| `review_progress.md` | 复习进度记录 |

**触发方式**：对 AI 说 `复习项目`、`带我复习`

**9 章内容**：

| 章节 | 主题 | 题数 |
|------|------|------|
| 第 1 章 | 项目全景与设计理念 | 8 题 |
| 第 2 章 | 数据摄取流水线 | 18 题 |
| 第 3 章 | 检索查询流水线 | 11 题 |
| 第 4 章 | MCP 服务设计 | 7 题 |
| 第 5 章 | 可插拔架构设计 | 6 题 |
| 第 6 章 | 可观测性与 Dashboard | 6 题 |
| 第 7 章 | 评估体系 | 5 题 |
| 第 8 章 | 测试体系与工程质量 | 5 题 |
| 第 9 章 | 存储与持久化架构 | 5 题 |

**教学原则**：不超前（不提前给答案）、不跳题（按顺序）、多鼓励、联系代码、控制节奏

---

### 元技能

#### 9. `skill-creator` — Skill 创建器

**功能**：指导你创建新的 Agent Skill（或修改已有 Skill）

| 组成 | 作用 |
|-----|------|
| `SKILL.md` | 5 步：理解需求 → 规划内容 → 初始化 → 编辑 → 迭代 |
| `references/workflows.md` | 多步骤工作流设计模式 |
| `references/output-patterns.md` | 输出格式和质量标准模式 |
| `scripts/init_skill.py` | 一键初始化 Skill 目录结构 |
| `scripts/package_skill.py` | 打包 Skill |
| `scripts/quick_validate.py` | 快速校验 Skill 格式 |

**触发方式**：对 AI 说 `create skill`、`新建 skill`

**Skill 结构**：
```
skill-name/
├── SKILL.md          (必需：frontmatter + 指令)
└── bundled resources (可选)
    ├── scripts/      — 可执行代码（确定性、可复用）
    ├── references/   — 按需加载的文档
    └── assets/       — 输出用资源（模板、图片等）
```

**核心原则**：
- 精简为王：只加 agent 不知道的信息
- 渐进披露：metadata(始终) → SKILL.md body(触发时) → resources(按需)
- 适当自由度：脆弱操作→低自由度(脚本)，灵活场景→高自由度(文本指令)

---

## 二、Skill 使用时机总结

| 项目阶段 | 使用的 Skill | 说明 |
|---------|-------------|------|
| 开发编码 | `auto-coder` | 逐任务推进，核心 Skill |
| 环境配置 | `setup` | Ingestion 完成后首次配置 |
| 全面测试 | `qa-tester` | 项目完成后全面验证 |
| 清理分发 | `package` | 交付前清理脱敏 |
| 写简历 | `resume-writer` | 准备求职材料 |
| 模拟面试 | `interview-prep` | 面试前实战演练 |
| 项目学习 | `project-learner` | 45知识点系统学习 |
| 项目复习 | `project-review` | 9章71题系统复习 |
| 创建新 Skill | `skill-creator` | 扩展项目能力 |

---

## 三、`.claude/skills/` 与 `.github/skills/` 的区别

### 核心区别：面向不同的 AI 工具

| 目录 | 面向的 AI 工具 | 说明 |
|------|--------------|------|
| `.claude/skills/` | **Claude Code**（Anthropic 的 CLI 工具） | Claude Code 读取 `.claude/` 目录下的 Skill |
| `.github/skills/` | **GitHub Copilot**（VS Code 中的 Copilot） | Copilot 读取 `.github/` 目录下的 Skill |

两个目录的存在是为了让**不同的 AI 编码助手**都能使用这些 Skill。你用哪个工具开发，对应的目录就会被读取。

### Skill 数量差异

| 目录 | Skill 数量 | 包含的 Skill |
|------|-----------|-------------|
| `.claude/skills/` | **4 个**（精简版） | auto-coder / qa-tester / resume-writer / skill-creator |
| `.github/skills/` | **9 个**（完整版） | auto-coder / qa-tester / resume-writer / skill-creator / setup / package / interview-prep / project-learner / project-review |

`.github/skills/` 多出 5 个 Skill：`setup`、`package`、`interview-prep`、`project-learner`、`project-review`

### 内容差异

同名 Skill 在两个目录下的**逻辑内容完全一致**，唯一的区别是**文件路径引用不同**：

```diff
# .claude/skills/auto-coder/SKILL.md
- python .claude/skills/auto-coder/scripts/sync_spec.py
- Read `.claude/skills/auto-coder/references/06-schedule.md`

# .github/skills/auto-coder/SKILL.md
+ python .github/skills/auto-coder/scripts/sync_spec.py
+ Read `.github/skills/auto-coder/references/06-schedule.md`
```

这是因为不同 AI 工具会从不同的根目录去查找 Skill 资源，所以路径前缀必须匹配。

此外，`.github/skills/qa-tester/` 比 `.claude/skills/qa-tester/` 多出两个文件：
- `QA_TEST_PLAN.md` — 完整测试计划
- `QA_TEST_PROGRESS.md` — 测试执行进度

以及部分同名脚本文件内容有差异（qa_bootstrap.py、qa_config.py 等），说明 `.github/` 下的版本更新更频繁。

### 使用建议

- **用 GitHub Copilot 开发**：Skill 从 `.github/skills/` 加载，9 个 Skill 全部可用
- **用 Claude Code 开发**：Skill 从 `.claude/skills/` 加载，只有 4 个核心 Skill
- **用 CatPaw（当前工具）开发**：两个目录的 Skill 都可能被识别，优先以 `.github/skills/` 为准（内容更完整）
- **如果需要缺失的 Skill**：可以把 `.github/skills/` 下缺失的 Skill 复制到 `.claude/skills/`，修改路径前缀即可

---

## 四、阶段 A1 知识点：初始化目录树与最小可运行入口

### 4.1 pyproject.toml — Python 项目配置标准

#### 为什么用 pyproject.toml 而不是 setup.py？

| 格式 | 时代 | 问题 |
|------|------|------|
| `setup.py` | Python 2.x-3.x | 可执行脚本，存在安全风险；格式不统一 |
| `pyproject.toml` | PEP 518 (2016) / PEP 621 (2020) | 声明式 TOML 格式，不可执行代码；字段标准化 |

**关键 PEP**：
- **PEP 518**：定义了 `pyproject.toml` 作为项目配置标准，`[build-system]` 表声明构建工具
- **PEP 621**：定义了 `[project]` 表的标准字段（name, version, dependencies 等），统一元数据格式

#### 为什么用 hatchling 而不是 setuptools？

| 构建后端 | 特点 |
|---------|------|
| `setuptools` | 老牌稳定，但配置复杂、构建慢 |
| `hatchling` | Hatch 项目的构建后端，更现代、更快、配置简洁 |
| `flit-core` | 最精简，适合纯 Python 包 |
| `poetry-core` | Poetry 的构建后端，但 Poetry 的依赖解析有兼容性问题 |

#### src layout（源码放在 src/ 下）

**核心原因**：
1. **防止意外导入**：如果源码在根目录，`python` 可能直接 import 到本地源码而非安装的包，导致测试不准确
2. **强制正确安装**：必须 `pip install -e .` 后才能 import，确保包是可以被正确安装的
3. **清晰边界**：`src/` = 你的代码，项目根 = 项目元数据

#### 可选依赖组 `[project.optional-dependencies]`

```toml
[project.optional-dependencies]
dev = ["pytest>=7.0", "ruff>=0.1.0"]  # pip install -e ".[dev]"
openai = ["openai>=1.0"]               # pip install -e ".[openai]"
all = ["smart-knowledge-hub[dev,openai,...]"]  # pip install -e ".[all]"
```

**面试考点**："如何管理开发依赖和生产依赖？" → 可选依赖组

---

### 4.2 .gitignore — 版本控制忽略规则

#### 核心原则：只提交源码和配置，不提交生成物和敏感信息

| 忽略类别 | 原因 | 面试追问 |
|---------|------|---------|
| `__pycache__/` | 字节码缓存，可随时重新生成，不同 Python 版本不兼容 | "Python 的 `__pycache__` 是什么？" |
| `.venv/` | 虚拟环境包含二进制文件，体积大(100MB+)，平台相关 | "为什么不提交 .venv？" |
| `.env` | 包含 API Key 等敏感信息，**绝不能提交** | "如何安全地管理 API Key？" |
| `data/`, `logs/`, `cache/` | 运行时产物，每个环境独立生成 | "什么是运行时产物？" |
| `*.egg-info/`, `dist/`, `build/` | pip install / build 时自动生成的打包产物 | "Python 打包流程？" |

#### .gitkeep 的作用

Git 不跟踪空目录，在空目录中放 `.gitkeep` 文件可以让 Git 跟踪该目录。`.gitkeep` 不是 Git 官方功能，只是一个约定俗成的空文件名。

---

### 4.3 Python 包与 `__init__.py`

#### 包 vs 目录

| 条件 | 是否是 Python 包 | 能否被 import |
|------|-----------------|-------------|
| 目录 + `__init__.py` | ✅ 是 | ✅ 可以 |
| 目录，无 `__init__.py` | ⚠️ 命名空间包（Python 3.3+） | 可能有意外行为 |
| 单个 `.py` 文件 | ✅ 是（模块） | ✅ 可以 |

**建议**：始终显式创建 `__init__.py`，即使内容为空。这是最清晰的做法。

---

### 4.4 五层架构设计（核心设计决策）

```
┌──────────────────────────────────────────────┐
│  MCP Clients (Copilot / Claude Desktop)      │
└──────────────────┬───────────────────────────┘
                   │ JSON-RPC 2.0 (Stdio)
┌──────────────────▼───────────────────────────┐
│  mcp_server — 接口层                          │
│  职责：协议解析、工具注册、对外暴露            │
└──────────────────┬───────────────────────────┘
┌──────────────────▼───────────────────────────┐
│  core — 业务层                                │
│  职责：检索引擎、数据契约、追踪、响应构建      │
└──────────────────┬───────────────────────────┘
┌──────────────────▼───────────────────────────┐
│  ingestion — 摄取层                           │
│  职责：Pipeline 编排，文档→Chunk→向量         │
└──────────────────┬───────────────────────────┘
┌──────────────────▼───────────────────────────┐
│  libs — 抽象层（可插拔）                      │
│  职责：Base接口 + Factory + 默认实现          │
└──────────────────┬───────────────────────────┘
┌──────────────────▼───────────────────────────┐
│  observability — 可观测层                     │
│  职责：日志、Dashboard、评估                   │
└──────────────────────────────────────────────┘
```

**依赖方向：从上到下，上层依赖下层，下层不知道上层的存在。**

为什么这样分层？
- **libs 层**：LLM/Embedding/Reranker 可以独立替换，不影响 core
- **core 层**：检索逻辑不关心底层用的是 OpenAI 还是 Ollama
- **mcp_server 层**：只负责协议，业务逻辑全在 core
- **observability 层**：横切关注点，被所有层调用但不依赖业务逻辑

**面试考点**："为什么用分层架构？" → 依赖隔离、可替换性、关注点分离

---

### 4.5 配置驱动设计 (Configuration-Driven)

#### 为什么用 YAML 而不是代码常量？

| 方案 | 修改方式 | 需要重启？ | 面试考点 |
|------|---------|----------|---------|
| 代码常量 | 改代码 → 重新部署 | 是 | 耦合度高 |
| YAML 配置 | 改配置 → 重启服务 | 是（本项目） | 配置与代码分离 |
| 环境变量 | 改环境变量 → 重启 | 取决于实现 | 适合容器化 |
| 配置中心 | 远程修改 → 热更新 | 否 | 适合微服务 |

#### Fail-Fast 原则

启动时校验所有必填字段，缺失直接报错退出。好处：
- **避免运行时崩溃**：配置问题尽早发现
- **错误信息清晰**："缺少 embedding.provider"比"AttributeError: NoneType"好理解100倍
- **A3 阶段实现**：`validate_settings()` 函数

#### API Key 安全

```yaml
api_key: "${OPENAI_API_KEY}"  # 从环境变量读取
```

- 绝不将 API Key 硬编码在配置文件中
- `.env` 文件在 `.gitignore` 中，不会被提交
- 运行时通过环境变量注入

---

### 4.6 MCP 协议与 Stdio Transport

#### MCP (Model Context Protocol) 是什么？

Anthropic 定义的 AI 工具调用标准协议：
- **MCP Server** 暴露 tools（工具）和 resources（资源）
- **MCP Client**（如 Copilot、Claude Desktop）连接 Server 调用工具
- 通信方式：JSON-RPC 2.0

#### Stdio Transport 的关键约束

```
stdin  ← 接收 Client 的 JSON-RPC 请求
stdout → 输出 Server 的 JSON-RPC 响应（只能输出 MCP 消息！）
stderr → 输出日志、调试信息（所有非 MCP 内容必须走 stderr）
```

**为什么这么严格？** stdout 的内容会被 Client 按 JSON-RPC 协议解析，任何非 JSON 输出都会导致协议错误。

---

### 4.7 虚拟环境 (Virtual Environment)

#### 为什么需要虚拟环境？

| 问题 | 没有虚拟环境 | 有虚拟环境 |
|------|-----------|----------|
| 依赖冲突 | 项目A需要 lib v1，项目B需要 lib v2 | 每个项目独立安装 |
| 系统污染 | 误装包可能影响系统 Python | 完全隔离 |
| 可复现性 | "我机器上能跑" | requirements.txt 锁定版本 |

#### 创建步骤

```bash
python3.12 -m venv .venv          # 创建虚拟环境
source .venv/bin/activate         # 激活（macOS/Linux）
pip install -e ".[dev]"           # 安装项目依赖（开发模式）
```

**`pip install -e .`** 的 `-e` 表示 editable（开发模式），代码修改后不需要重新安装就能生效。

---

### 4.8 面试高频问题速查

| 问题 | 关键答案 |
|------|---------|
| "为什么用 pyproject.toml？" | PEP 518/621 标准，声明式，不可执行代码 |
| "为什么用 src layout？" | 防止意外导入未安装的包，强制正确安装 |
| "Python 包和目录的区别？" | 含 `__init__.py` 的是包，可以被 import |
| "为什么分层？" | 依赖隔离、可替换性、关注点分离 |
| "什么是工厂模式？" | 将"创建哪个实现"的决策从业务代码中解耦 |
| "为什么用 YAML 配置？" | 配置与代码分离，修改不需改代码 |
| "MCP Stdio 约束？" | stdout 只输出 JSON-RPC，日志走 stderr |
| "为什么需要虚拟环境？" | 依赖隔离，避免版本冲突，可复现 |
| "Fail-Fast 是什么？" | 启动时校验必填字段，缺失直接报错退出 |
| "API Key 怎么管理？" | 环境变量注入，不硬编码，.env 不提交 |

---

## 五、全项目 9 阶段总览（做什么 + 需要弄懂的知识点）

### 阶段 A：工程骨架与测试基座（3 个任务：A1-A3）

**做什么**：搭建可运行、可配置、可测试的工程骨架

| 任务 | 做什么 | 需要弄懂的知识点 |
|------|--------|----------------|
| A1 | 创建目录树、pyproject.toml、虚拟环境、`__init__.py`、config 占位 | pyproject.toml / PEP 518/621 / src layout / Python 包与 `__init__.py` / 五层架构 / 配置驱动 / MCP Stdio 约束 / 虚拟环境 / .gitignore |
| A2 | 引入 pytest，建立 tests/unit/integration/e2e/fixtures 目录，写冒烟测试 | pytest 配置 / 测试分层（unit/integration/e2e）/ marker 标记 / pythonpath 配置 / 冒烟测试的意义 |
| A3 | 实现 Settings dataclass + load_settings() + validate_settings()，main.py 调用 | dataclass / YAML 解析 / Fail-Fast 原则 / 环境变量替换 / 配置校验 vs 业务初始化的区别 |

---

### 阶段 B：Libs 可插拔层（16 个任务：B1-B9）

**做什么**：实现"可替换变成代码事实"——抽象接口 + 工厂模式 + 默认可运行实现

| 任务 | 做什么 | 需要弄懂的知识点 |
|------|--------|----------------|
| B1-B6 | 定义 6 组抽象接口 + 工厂（LLM/Embedding/Splitter/VectorStore/Reranker/Evaluator） | **工厂模式** / **抽象基类(ABC)** / 接口隔离原则 / 配置驱动切换 / 优雅降级 |
| B7.1-B7.2 | OpenAI Compatible + Ollama LLM 实现 | OpenAI SDK / Ollama REST API / 继承 BaseLLM / Fake Provider 测试 |
| B7.3-B7.4 | OpenAI/Azure + Ollama Embedding 实现 | Embedding 原理 / 维度(dimension) / 批量 embed |
| B7.5 | RecursiveCharacterTextSplitter 实现 | LangChain text-splitters / Markdown 结构切分 / chunk_size / chunk_overlap |
| B7.6 | ChromaStore 默认实现 | ChromaDB 嵌入式架构 / upsert 幂等性 / metadata 过滤 / cosine similarity |
| B7.7-B7.8 | LLM Reranker + Cross-Encoder Reranker 实现 | CrossEncoder vs Bi-Encoder / sentence-transformers / 精排 vs 粗排 |
| B8-B9 | Vision LLM 抽象 + Azure Vision 实现 | 多模态 API / Base64 图片编码 / Image Captioning 架构 |

**🔥 本阶段是面试核心**：工厂模式、抽象基类、可插拔架构的设计思路，面试必问。

---

### 阶段 C：Ingestion Pipeline（15 个任务：C1-C15）

**做什么**：离线摄取链路跑通——PDF→Markdown→Chunk→Embedding→Upsert

| 任务 | 做什么 | 需要弄懂的知识点 |
|------|--------|----------------|
| C1 | 定义 Document/Chunk/ChunkRecord 数据契约 | dataclass 设计 / 契约中心模式 / ID 生成策略（`{doc_id}_{index:04d}_{hash}`） |
| C2 | SHA256 文件完整性检查 | SHA256 原理 / 增量摄取（跳过未变更文件）/ 幂等性 |
| C3 | BaseLoader + PDF Loader（MarkItDown） | PDF 解析原理 / Markdown 中间格式 / 为什么先转 Markdown 再切分 |
| C4 | Splitter 集成 | 调用 libs.splitter / metadata 继承 / source_ref 溯源 |
| C5 | BaseTransform + ChunkRefiner | Transform 链 / 原子化 / 幂等性 / 降级安全 |
| C6 | MetadataEnricher | Title/Summary/Tags 生成 / LLM 增强 vs 规则生成 |
| C7 | ImageCaptioner | Vision LLM 调用 / 降级模式 / has_unprocessed_images 标记 |
| C8-C9 | DenseEncoder + SparseEncoder | 批量 embed / BM25 统计（TF/IDF/文档长度） |
| C10 | BatchProcessor | 分批策略 / 批次耗时记录 |
| C11 | BM25Indexer | **倒排索引构建** / **IDF 计算** / pickle 持久化 |
| C12 | VectorUpserter | 幂等 upsert / 稳定 ID / metadata 完整性 |
| C13 | ImageStorage | 文件存储 + SQLite 索引映射 / image_id 查询 |
| C14 | Pipeline 编排 | Pipeline 模式 / on_progress 回调 / 增量 vs 全量 |
| C15 | ingest.py 脚本入口 | argparse CLI 设计 / --collection / --path / --force |

**🔥 核心考点**：Chunking 策略（为什么先转 Markdown）、幂等性（重复运行不出错）、增量摄取（SHA256 判断变更）

---

### 阶段 D：Retrieval MVP（7 个任务：D1-D7）

**做什么**：在线查询链路跑通——Dense + Sparse + RRF + Rerank

| 任务 | 做什么 | 需要弄懂的知识点 |
|------|--------|----------------|
| D1 | QueryProcessor | 关键词提取 / 同义词扩展 / Metadata 过滤解析 |
| D2 | DenseRetriever | Query Embedding → VectorStore 检索 / cosine similarity |
| D3 | SparseRetriever | BM25 查询 / 倒排索引检索 / TF-IDF 打分 |
| D4 | RRF Fusion | **RRF 算法原理** / k=60 平滑常数 / 为什么不直接加权融合 |
| D5 | HybridSearch 编排 | **并行 Dense + Sparse** / Metadata 后置过滤 / 单路降级 |
| D6 | Reranker | CrossEncoder 精排 / fallback 回退 / fallback=true 标记 |
| D7 | query.py 脚本入口 | --query / --top-k / --verbose / --no-rerank |

**🔥 面试最高频**：Hybrid Search 为什么比单一检索好？RRF 怎么解决分数量纲不同问题？两段式架构（粗排→精排）的设计？

---

### 阶段 E：MCP Server 层与 Tools（6 个任务：E1-E6）

**做什么**：按 MCP 标准暴露 tools，让 Copilot/Claude 可直接调用

| 任务 | 做什么 | 需要弄懂的知识点 |
|------|--------|----------------|
| E1 | MCP Server 入口 + Stdio 约束 | **MCP 协议** / JSON-RPC 2.0 / stdin/stdout/stderr 分离 / 子进程测试 |
| E2 | Protocol Handler | initialize 能力协商 / tools/list Schema / tools/call 路由 / 错误码规范 |
| E3 | query_knowledge_hub Tool | MCP Tool Schema / inputSchema / Citation 透明性 |
| E4 | list_collections Tool | 工具注册 / 响应格式 |
| E5 | get_document_summary Tool | 文档摘要 / 结构化返回 |
| E6 | 多模态返回组装 | TextContent + ImageContent / Base64 编码 / 兼容原则（第一项必为文本） |

**🔥 考点**：MCP 协议是什么？与 Function Calling 的关系？Stdio Transport 为什么 stdout 不能混用？

---

### 阶段 F：Trace 基础设施与打点（5 个任务：F1-F5）

**做什么**：增强 TraceContext，实现结构化日志持久化，双链路打点

| 任务 | 做什么 | 需要弄懂的知识点 |
|------|--------|----------------|
| F1 | TraceContext 增强 | trace_type（query/ingestion） / stages[] / finish() 耗时统计 / to_dict() 序列化 |
| F2 | JSON Lines 日志 | JSONL 格式 / 结构化日志 vs 纯文本日志 / 日志轮转 |
| F3 | Query 链路打点 | 各阶段（dense/sparse/fusion/rerank）的候选数、分数分布、耗时 |
| F4 | Ingestion 链路打点 | 各阶段（load/split/transform/embed/upsert）的处理数量、跳过/失败详情 |
| F5 | Pipeline 进度回调 | on_progress(stage, current, total) / Dashboard 进度条驱动 |

**考点**：为什么需要 Trace？JSONL vs 传统日志？低侵入性追踪怎么做？

---

### 阶段 G：可视化管理平台 Dashboard（6 个任务：G1-G6）

**做什么**：搭建 Streamlit 六页面管理平台

| 任务 | 做什么 | 需要弄懂的知识点 |
|------|--------|----------------|
| G1 | Dashboard 基础架构 + 系统总览页 | Streamlit 多页面 / st.navigation() / ConfigService / 动态组件渲染 |
| G2 | DocumentManager | **跨 4 个存储协调删除**（Chroma/BM25/ImageStorage/FileIntegrity）/ 幂等管理 |
| G3 | 数据浏览器 | 文档列表 / Chunk 详情 / 图片预览 |
| G4 | Ingestion 管理页面 | 文件上传 / 摄取触发 / st.progress() 实时进度 |
| G5 | Ingestion 追踪页面 | TraceService 读取 / 按 trace_type 分类 |
| G6 | Query 追踪页面 | 耗时瀑布图 / Dense vs Sparse 召回对比 / Rerank 前后排名 |

**考点**：Streamlit 架构 / DocumentManager 跨存储一致性 / Dashboard 动态渲染原理

---

### 阶段 H：评估体系（5 个任务：H1-H5）

**做什么**：实现评估框架 + Golden Test Set 回归

| 任务 | 做什么 | 需要弄懂的知识点 |
|------|--------|----------------|
| H1 | RagasEvaluator | Ragas 框架 / Faithfulness / Answer Relevancy / Context Precision / 优雅降级 |
| H2 | CompositeEvaluator | **组合模式** / 多 Evaluator 并行执行 / metrics 合并 |
| H3 | EvalRunner + Golden Test Set | golden_test_set.json 格式 / Hit Rate / MRR / 评估脚本 |
| H4 | 评估面板页面 | 运行评估 / 指标展示 / 历史对比 |
| H5 | Recall 回归测试 | E2E 测试 / hit@k 阈值 / 回归基线 |

**🔥 考点**：Ragas 评估框架 / Faithfulness 是什么意思 / Hit Rate 和 MRR 怎么算 / 为什么要建立回归基线

---

### 阶段 I：端到端验收与文档收口（5 个任务：I1-I5）

**做什么**：E2E 测试 + Dashboard 冒烟 + README 完善 + 契约测试 + 全链路验收

| 任务 | 做什么 | 需要弄懂的知识点 |
|------|--------|----------------|
| I1 | MCP Client 模拟测试 | 子进程启动 Server / JSON-RPC 请求模拟 / tools/list + tools/call |
| I2 | Dashboard 冒烟测试 | Streamlit AppTest / 6 页面无异常渲染 |
| I3 | 完善 README | 快速开始 / 配置说明 / MCP 配置 / Dashboard 使用 / 测试命令 |
| I4 | 契约测试补齐 | VectorStore/Reranker/Evaluator 接口契约 / 输入输出形状验证 |
| I5 | 全链路 E2E 验收 | ingest → query → MCP → Dashboard → evaluate 全流程跑通 |

**考点**：E2E 测试与单元测试的区别 / 契约测试是什么 / 为什么要"开箱即用 + 可复现"

---

### 📌 各阶段面试权重

| 权重 | 阶段 | 面试最常问的内容 |
|------|------|----------------|
| ⭐⭐⭐ | **B（可插拔层）** | 工厂模式、ABC、如何设计可扩展架构 |
| ⭐⭐⭐ | **D（Retrieval）** | Hybrid Search 原理、RRF、两段式检索 |
| ⭐⭐ | **C（Ingestion）** | Chunking 策略、幂等性、增量摄取 |
| ⭐⭐ | **E（MCP Server）** | MCP 协议、JSON-RPC、Stdio Transport |
| ⭐ | A/F/G/H/I | 工程化能力，不是核心考点但会追问细节 |

> **建议学习路线**：A1→A2→A3→B1→B2→...→D1→D2→...（按顺序做，后面依赖前面）

---

## 六、阶段 A2 知识点：引入 pytest 并建立测试目录约定

### 6.1 测试分层策略

| 测试类型 | 目的 | 速度 | 外部依赖 | pytest 标记 |
|---------|------|------|---------|------------|
| **Unit** | 验证单个函数/类的逻辑 | 毫秒级 | ❌ 全部 Mock | `@pytest.mark.unit` |
| **Integration** | 验证多个模块协作 | 秒级 | ⚠️ 可能需要真实 DB | `@pytest.mark.integration` |
| **E2E** | 验证完整用户链路 | 分钟级 | ✅ 完整系统运行 | `@pytest.mark.e2e` |

**面试考点**："为什么不能只写 E2E 测试？" → 太慢、失败难定位、维护成本高。大部分 bug 应在单元测试阶段发现。

---

### 6.2 pytest 核心机制

#### 测试发现规则

```
1. 文件名以 test_ 开头或 _test 结尾 → 被识别为测试文件
2. 函数名以 test_ 开头 → 被识别为测试函数
3. 类名以 Test 开头（且不含 __init__）→ 被识别为测试类
4. conftest.py → 自动加载的共享配置，不需要 import
```

#### fixture 依赖注入机制

```python
# 定义 fixture（在 conftest.py 中）
@pytest.fixture(scope="session")
def config_path(project_root: Path) -> Path:
    return project_root / "config" / "settings.yaml"

# 使用 fixture（在测试函数中，通过参数名引用）
def test_config_exists(config_path):    # ← pytest 自动注入 config_path 的返回值
    assert config_path.exists()
```

**关键接口签名**：

| fixture | 签名 | 返回值 | scope |
|---------|------|--------|-------|
| `project_root` | `project_root() -> Path` | 项目根目录 | session |
| `config_path` | `config_path(project_root: Path) -> Path` | `config/settings.yaml` 路径 | session |
| `fixtures_dir` | `fixtures_dir(project_root: Path) -> Path` | `tests/fixtures/` 路径 | session |
| `sample_documents_dir` | `sample_documents_dir(fixtures_dir: Path) -> Path` | `tests/fixtures/sample_documents/` 路径 | session |

**fixture scope 详解**：

| scope | 执行次数 | 适用场景 |
|-------|---------|---------|
| `function` | 每个测试函数一次（默认） | 需要干净状态的测试 |
| `class` | 每个测试类一次 | 类内共享状态 |
| `module` | 每个测试文件一次 | 文件内共享数据 |
| `session` | 整个测试会话一次 | 昂贵的初始化（如数据库连接） |

---

### 6.3 conftest.py 层级机制

```
tests/
├── conftest.py          ← 所有测试可见（全局 fixture）
├── unit/
│   ├── conftest.py      ← 仅 unit/ 下测试可见
│   └── test_xxx.py
├── integration/
│   ├── conftest.py      ← 仅 integration/ 下测试可见
│   └── test_yyy.py
└── e2e/
    ├── conftest.py      ← 仅 e2e/ 下测试可见
    └── test_zzz.py
```

**面试考点**："conftest.py 的作用？" → 共享 fixture + 路径配置 + 钩子函数（如 pytest_configure）

---

### 6.4 冒烟测试 (Smoke Test) 设计

```python
# 冒烟测试函数签名
def test_import_mcp_server() -> None:
    """验证 mcp_server 包可导入 — 无入参，断言通过即成功"""
    import mcp_server
    assert mcp_server is not None
```

**为什么写冒烟测试？**
- 如果 import 都失败，后续所有测试都没有意义
- 冒烟测试是"第一道防线"，在 CI 中最先运行
- 12 个冒烟测试覆盖：5 个顶层包 + 4 组子模块 + 1 个 YAML 依赖 + 2 个路径校验

---

### 6.5 yaml.safe_load vs yaml.load

```python
# ✅ 安全：safe_load 只解析基本 YAML 类型
result = yaml.safe_load("key: value")  # → {"key": "value"}

# ❌ 危险：load 可以执行任意 Python 代码
result = yaml.load("!!python/object/apply:os.system ['rm -rf /']", Loader=yaml.UnsafeLoader)
```

**面试考点**："为什么用 yaml.safe_load？" → 防止 YAML 反序列化攻击。`yaml.load()` 可以执行任意 Python 代码（通过 `!!python/object` 标签），`safe_load` 限制了可解析的类型。

---

### 6.6 pytest 配置详解（pyproject.toml 中）

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]              # 只在 tests/ 下查找测试
markers = [                         # 自定义标记
    "unit: 单元测试",
    "integration: 集成测试",
    "e2e: 端到端测试",
    "slow: 慢速测试",
]
addopts = "-ra -q --strict-markers" # -ra: 显示非通过摘要; -q: 安静; --strict-markers: 未注册标记报错
pythonpath = ["src"]                # 让 pytest 能 import src/ 下的包
```

**面试考点**："`--strict-markers` 的作用？" → 使用未注册的 marker 会报错而非警告，防止拼写错误导致的测试分类遗漏。

---

### 6.7 A2 面试高频问题

| 问题 | 关键答案 |
|------|---------|
| "测试为什么要分层？" | 速度不同、定位精度不同、维护成本不同 |
| "pytest fixture 和 unittest setUp 的区别？" | fixture 是依赖注入，支持参数化、作用域控制、组合复用 |
| "conftest.py 的作用？" | 全局共享 fixture + 钩子函数，自动发现无需 import |
| "fixture 的 scope 有哪些？" | function/class/module/session |
| "为什么用 yaml.safe_load？" | 防止 YAML 反序列化攻击 |
| "冒烟测试测什么？" | 只测包能否导入，不测业务逻辑 |

---

## 7. A3：配置加载与校验（Settings）

### 7.1 目标

实现读取 `config/settings.yaml` 的配置加载器，并在启动时校验关键字段存在（Fail-Fast）。

### 7.2 关键设计决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 配置数据结构 | dataclass（非 dict/pydantic） | 零依赖 + 类型提示 + IDE 补全 |
| 配置校验方式 | 独立 validate_settings() | 分离加载和校验，测试更灵活 |
| 环境变量替换 | ${VAR} 格式 | Bash 风格，直观 |
| dict→dataclass | 手写映射表 | `from __future__ annotations` 导致 f.type 为字符串 |

### 7.3 关键接口签名（面试必须掌握）

```python
# ---- 自定义异常 ----
class SettingsError(Exception):
    """配置错误，错误信息包含字段路径如 "embedding.provider" """

# ---- 核心函数 ----
load_settings(path: str = "config/settings.yaml") -> Settings
    # 入参：YAML 配置文件路径
    # 出参：Settings 对象（dataclass 树）
    # 异常：SettingsError — 文件不存在 / YAML解析失败 / 字段校验失败
    # 流程：读文件 → yaml.safe_load() → 替换${VAR} → dict→dataclass → validate

validate_settings(settings: Settings) -> None
    # 入参：Settings 对象
    # 出参：None（校验通过）或抛出 SettingsError
    # 校验：llm.provider, llm.model, embedding.provider, embedding.model 必填
    #       embedding.dimensions > 0
    #       vision_llm.enabled=true 时 provider/model 必填
    #       rerank.enabled=true 时 backend 必填

# ---- 日志 ----
get_logger(name: str = "rag", level: str = "INFO") -> logging.Logger
    # 入参：logger名称、日志级别
    # 出参：标准 logging.Logger 实例
    # 关键：输出到 stderr（MCP 协议 stdout 被 JSON-RPC 占用）
```

### 7.4 数据流

```
config/settings.yaml
    │
    ▼
yaml.safe_load()  ──→  dict (原始)
    │
    ▼
_resolve_env_vars_recursive()  ──→  dict (${VAR} → os.environ值)
    │
    ▼
_dict_to_dataclass(Settings, dict)  ──→  Settings dataclass 树
    │                                         ├── settings.llm: LLMSettings
    │                                         ├── settings.embedding: EmbeddingSettings
    │                                         ├── settings.vision_llm: VisionLLMSettings
    │                                         ├── settings.vector_store: VectorStoreSettings
    │                                         ├── settings.retrieval: RetrievalSettings
    │                                         ├── settings.rerank: RerankSettings
    │                                         ├── settings.evaluation: EvaluationSettings
    │                                         ├── settings.observability: ObservabilitySettings
    │                                         └── settings.dashboard: DashboardSettings
    │
    ▼
validate_settings(settings)  ──→  None (通过) 或 SettingsError
    │
    ▼
main.py: logger.info("配置加载成功: LLM=openai/gpt-4o, Embedding=openai/text-embedding-3-small")
```

### 7.5 子配置类结构 — 9 个子 dataclass 的用途

**为什么要拆成 9 个子 dataclass？**

核心原因：YAML 配置文件是分 section 组织的（如 `llm:`、`embedding:`），每个 section 对应一个子 dataclass，实现"一对一映射"。这样做的好处：

1. **类型安全**：`settings.llm.provider` 有类型提示和 IDE 补全，`settings["llm"]["provider"]` 没有
2. **单一职责**：每个子配置类只管自己的字段，改 LLM 配置不会影响 Embedding
3. **校验粒度**：每个子配置可以有独立的校验规则（如 `embedding.dimensions > 0`）
4. **向前兼容**：YAML 中新增字段时，子 dataclass 用默认值兜底，老代码不报错

**类比理解**：如果把 Settings 看作一棵树，9 个子 dataclass 就是 9 个树枝，每个树枝只负责自己领域的配置叶子。

```
Settings（根）
  ├── LLMSettings          ← 控制"用哪个大模型生成回答"
  ├── EmbeddingSettings     ← 控制"用哪个模型把文本变成向量"
  ├── VisionLLMSettings     ← 控制"图片描述功能用哪个视觉模型"
  ├── VectorStoreSettings   ← 控制"向量存到哪个数据库"
  ├── RetrievalSettings     ← 控制"怎么检索：稀疏/稠密/融合策略"
  ├── RerankSettings        ← 控制"检索后要不要重排序"
  ├── EvaluationSettings    ← 控制"怎么评估 RAG 系统效果"
  ├── ObservabilitySettings ← 控制"日志/追踪怎么记录"
  └── DashboardSettings     ← 控制"管理后台怎么启动"
```

**各子 dataclass 详细说明**：

| dataclass | 用途 | 关键字段 | 必填 | 对应 RAG 阶段 |
|-----------|------|---------|------|--------------|
| `LLMSettings` | 控制生成回答的大模型。`provider` 决定用 OpenAI/Azure/Ollama/DeepSeek 哪家 SDK，`model` 决定具体模型 | provider, model, api_key, azure_endpoint, base_url | provider ✅ model ✅ | 生成阶段（Generation） |
| `EmbeddingSettings` | 控制文本→向量的 Embedding 模型。`dimensions` 决定向量维度，必须与模型匹配（如 text-embedding-3-small = 1536） | provider, model, dimensions, api_key | provider ✅ model ✅ dimensions ✅(>0) | 索引阶段（Ingestion）+ 检索阶段（Retrieval） |
| `VisionLLMSettings` | 控制图片→文字描述的视觉模型。`enabled=false` 时跳过图片处理，节省资源 | enabled, provider, model | enabled=true时 provider ✅ model ✅ | 索引阶段（Ingestion）— 图片处理 |
| `VectorStoreSettings` | 控制向量存储后端。`backend` 决定用 ChromaDB/Qdrant/Pinecone，`persist_path` 决定数据存在哪 | backend, persist_path | - | 索引阶段 + 检索阶段 |
| `RetrievalSettings` | 控制混合检索策略。`fusion_algorithm` 决定 BM25+Dense 怎么融合（RRF/加权求和），`top_k_*` 控制各路召回数量 | sparse_backend, fusion_algorithm, top_k_dense/sparse/final | - | 检索阶段（Retrieval） |
| `RerankSettings` | 控制检索后的重排序。`enabled=false` 时跳过重排，`backend` 决定用 Cross-Encoder 还是 LLM 重排 | enabled, backend, model, top_m | enabled=true时 backend ✅ | 检索后处理（Post-Retrieval） |
| `EvaluationSettings` | 控制 RAG 系统效果评估。`backends` 决定用 ragas 还是自定义评估，`golden_test_set` 是黄金测试集路径 | backends, golden_test_set | - | 评估阶段（Evaluation） |
| `ObservabilitySettings` | 控制可观测性。`log_level` 控制日志级别，`detail_level` 控制追踪记录的详细程度（minimal/standard/verbose） | enabled, log_file, log_level, detail_level | - | 全链路（贯穿所有阶段） |
| `DashboardSettings` | 控制 Streamlit 管理后台。`port` 决定监听端口，`auto_refresh` 控制是否自动刷新追踪数据 | enabled, port, traces_dir, auto_refresh, refresh_interval | - | 运维监控 |

**使用示例（面试常问："Settings 对象长什么样？"）**：

```python
settings = load_settings()

# 访问各子配置 — 有类型提示 + IDE 补全
settings.llm.provider              # "openai"     — 生成回答用 GPT-4o
settings.llm.model                 # "gpt-4o"
settings.embedding.provider        # "openai"     — Embedding 用 OpenAI
settings.embedding.model           # "text-embedding-3-small"
settings.embedding.dimensions      # 1536         — 向量维度
settings.vision_llm.enabled        # True         — 启用图片描述
settings.vector_store.backend      # "chroma"     — 用 ChromaDB
settings.retrieval.fusion_algorithm # "rrf"       — RRF 融合
settings.retrieval.top_k_final     # 10           — 最终返回 10 条
settings.rerank.enabled            # False        — 暂不启用重排
settings.observability.log_level   # "INFO"
settings.dashboard.port            # 8501
```

### 7.6 Bug 修复记录

**Bug：`_dict_to_dataclass` 没有递归转换嵌套 dict 为 dataclass**

- **现象**：`settings.llm` 是 dict 而非 LLMSettings，访问 `.provider` 时 `AttributeError: 'dict' object has no attribute 'provider'`
- **根因**：`from __future__ annotations` 使 dataclass 的 `f.type` 变成字符串（如 `"LLMSettings"`），而非实际类型对象。`isinstance(f.type, type)` 始终为 False，导致嵌套 dict 不被递归转换
- **修复**：使用 `_FIELD_TYPE_MAP` 显式映射 `(类名, 字段名) → dataclass 类型`，替代运行时类型检查

```python
# 修复前（有 Bug）
if hasattr(f.type, '__dataclass_fields__') if isinstance(f.type, type) else False:
    kwargs[f.name] = _dict_to_dataclass(f.type, value)

# 修复后
field_type = _FIELD_TYPE_MAP.get((cls.__name__, f.name))
if field_type is not None and isinstance(value, dict):
    kwargs[f.name] = _dict_to_dataclass(field_type, value)
```

### 7.7 测试覆盖

| 测试类 | 用例数 | 覆盖场景 |
|--------|--------|---------|
| `TestLoadSettingsSuccess` | 4 | 最小配置、完整配置、默认值、多余字段忽略 |
| `TestLoadSettingsEnvVars` | 3 | ${VAR}替换、未设变量→空串、字符串中间嵌入 |
| `TestLoadSettingsErrors` | 4 | 文件不存在、空YAML、语法错误、YAML是list |
| `TestValidateSettings` | 10 | 各必填字段缺失、条件校验、多字段缺失、默认Settings |
| `TestLoadSettingsMissingFields` | 3 | YAML中缺失字段/section |

### 7.8 知识点详解

**1. 为什么选 dataclass 而不是 pydantic？**
- dataclass 是标准库，零依赖
- 校验逻辑自己实现，更灵活
- 项目核心是 RAG，不是配置管理，避免引入 pydantic 学习成本

**2. 为什么 MCP Server 日志必须走 stderr？**
- MCP 协议使用 stdio（stdin/stdout）传输 JSON-RPC 消息
- stdout 被协议独占，如果日志写到 stdout，会污染消息流导致协议解析失败
- stderr 是 MCP 规范推荐的日志输出通道

**3. yaml.safe_load vs yaml.load？**
- `yaml.load()` 支持自定义 Python 对象反序列化，可能导致远程代码执行（RCE）
- `yaml.safe_load()` 只支持基本类型（dict/list/str/int/float/bool/None），安全
- 面试考点：永远用 `yaml.safe_load()`

**4. `from __future__ annotations` 的副作用**
- 开启后所有类型注解变成字符串（PEP 563），延迟求值
- 优点：解决前向引用问题（A 类引用 B 类，B 类定义在后面）
- 副作用：`dataclass.fields()` 的 `f.type` 变成字符串，`isinstance(f.type, type)` 为 False
- 解决方案：用 `typing.get_type_hints(cls)` 获取实际类型，或用映射表

**5. Fail-Fast 原则**
- 启动时校验所有必填配置，缺失直接退出
- 优于运行时才发现配置错误（更难定位）
- 面试考点："为什么不在使用时才检查？" → 启动时发现问题 < 运行时发现问题

### 7.9 修改文件清单

| 文件 | 变更 |
|------|------|
| `src/core/settings.py` | **新增**：Settings dataclass 树 + load_settings + validate_settings |
| `src/observability/logger.py` | **新增**：get_logger 占位实现 |
| `main.py` | **更新**：调用 load_settings()，Fail-Fast 退出 |
| `config/settings.yaml` | 无变更（已在 A1 创建） |
| `tests/unit/test_config_loading.py` | **新增**：24 个测试用例 |

### 7.10 A3 面试高频问题

| 问题 | 关键答案 |
|------|---------|
| "配置加载的完整流程？" | 读文件→yaml.safe_load→替换${VAR}→dict→dataclass→validate |
| "为什么用 dataclass 不用 pydantic？" | 零依赖+自己校验更灵活+项目核心不在配置管理 |
| "MCP Server 为什么不能 print()？" | stdout 被 JSON-RPC 占用，print 会污染协议消息流 |
| "yaml.safe_load 和 yaml.load 区别？" | safe_load 只支持基本类型防RCE，load 支持自定义对象有安全风险 |
| "validate_settings 校验了什么？" | 必填字段存在 + 值合法 + 条件校验（enabled时子字段必填） |
| "from __future__ annotations 有什么副作用？" | f.type 变字符串，isinstance检查失败，需用映射表或get_type_hints |
| "Fail-Fast 原则是什么？" | 启动时校验所有配置，缺失直接退出，优于运行时才发现错误 |
| "修改配置文件后需要重启吗？" | 当前版本需要重启（启动时一次性加载）。未来可加热更新 |

### 7.11 配置热更新分析

**当前行为**：`load_settings()` 只在 `main.py` 启动时调用一次，修改 YAML 后必须重启进程才能生效。

**是否需要热更新？**

| 场景 | 是否需要 | 理由 |
|------|---------|------|
| 生产 MCP Server | ❌ | 配置变更应走正式发布流程，热更新有风险 |
| 开发调试 | ⚠️ 有用但非必须 | 改完重启也就几秒 |
| Dashboard 运维调参 | ✅ | 调 top_k、log_level 等参数时不想断开连接 |

**如果未来要做热更新，三种典型方案**：

| 方案 | 原理 | 优点 | 缺点 |
|------|------|------|------|
| 1. 定时轮询 | 每 N 秒检查文件 mtime，变了就 reload | 实现最简单 | 有延迟（N 秒），浪费 CPU |
| 2. watchdog 文件监听 | OS 级文件变更事件，变了立刻回调 | 实时 + 零轮询 | 需要额外依赖（watchdog 库） |
| 3. MCP 工具接口 | 暴露 `reload_config` MCP Tool，客户端主动调用 | 客户端控制时机 + 可校验后才生效 | 需要 MCP Server 已实现 |

**推荐路径**：当前 A3 阶段不做热更新。E1（MCP Server）阶段实现方案 3，通过 MCP Tool 暴露 `reload_config`，既安全又可控。

---

## 8. 项目待优化项（TODO）

> 随开发推进持续更新。每完成一个阶段，回顾此清单，将已解决的项标记 ~~删除线~~。

### 8.1 配置层

| # | 优化项 | 来源 | 优先级 | 建议实现阶段 | 说明 |
|---|--------|------|--------|------------|------|
| 1 | 配置热更新（reload_config MCP Tool） | A3 | P2 | E1 | 修改 YAML 后无需重启，通过 MCP Tool 主动触发 reload，校验通过才生效 |
| 2 | `${VAR:-default}` 带默认值的环境变量语法 | A3 | P3 | B+ | 当前 `${VAR}` 未设时返回空串；支持 `${VAR:-default}` 更安全 |
| 3 | 配置 schema 版本号 | A3 | P3 | E+ | YAML 顶部加 `version: 1`，未来升级配置结构时可做兼容迁移 |
| 4 | 配置变更审计日志 | A3 | P3 | F+ | 每次配置加载/热更新写入 audit log，方便排查"配置改了导致异常" |

### 8.2 架构层

| # | 优化项 | 来源 | 优先级 | 建议实现阶段 | 说明 |
|---|--------|------|--------|------------|------|
| 5 | `typing.get_type_hints()` 替代 `_FIELD_TYPE_MAP` | A3 Bug修复 | P2 | B | 当前用映射表解决 `from __future__ annotations` 问题，`get_type_hints()` 更优雅、可扩展 |
| 6 | Settings 单例模式 | A3 | P2 | E | 避免多处 `load_settings()` 重复读文件，全局持有一个 Settings 实例 |

### 8.3 安全层

| # | 优化项 | 来源 | 优先级 | 建议实现阶段 | 说明 |
|---|--------|------|--------|------------|------|
| 7 | API Key 明文告警 | A3 | P2 | B | `validate_settings` 中检测 api_key 是否为明文（非 `${VAR}` 格式），打印警告 |

### 8.4 测试层

| # | 优化项 | 来源 | 优先级 | 建议实现阶段 | 说明 |
|---|--------|------|--------|------------|------|
| 8 | 配置加载性能基准测试 | A3 | P3 | G+ | 测量 `load_settings()` 耗时，确保 < 100ms |

---

## 9. B1：LLM 抽象接口与工厂

### 9.1 目标

定义 `BaseLLM` 与 `LLMFactory`，支持按配置选择 LLM provider。用 Fake provider 验证工厂路由逻辑。

### 9.2 关键设计决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 抽象基类 | ABC + @abstractmethod | 编译期约束子类必须实现 chat() 和 model_name |
| 工厂模式 | 简单工厂（映射表） | Provider 数量少，映射表够用 |
| 测试策略 | FakeLLM 测试桩 | 隔离测试，不依赖真实 API，稳定可重复 |
| chat() 返回值 | str（非自定义 Response） | YAGNI 原则，当前不需要 usage/finish_reason |
| Provider 注册 | register() 方法 | 开放-封闭原则（OCP），新增 Provider 不改工厂代码 |

### 9.3 关键接口签名（面试必须掌握）

```python
# ---- 抽象基类 ----
class BaseLLM(ABC):
    @abstractmethod
    def chat(self, messages: list[dict], **kwargs) -> str
        # 入参：messages=[{"role": "system"/"user"/"assistant", "content": "..."}]
        # 出参：LLM 生成的文本字符串
        # 异常：LLMError

    @property
    @abstractmethod
    def model_name(self) -> str
        # 返回当前模型名称，用于日志和追踪

# ---- 工厂 ----
class LLMFactory:
    @classmethod
    def create(cls, settings: LLMSettings) -> BaseLLM
        # provider → _PROVIDERS 映射表 → llm_class(settings)

    @classmethod
    def register(cls, provider: str, llm_class: type[BaseLLM]) -> None
        # 注册新 Provider，实现开放-封闭原则

# ---- 测试桩 ----
class FakeLLM(BaseLLM):
    def __init__(self, settings: LLMSettings, response: str = "fake response")
    def chat(messages, **kwargs) -> str  # 返回预设 response
```

### 9.4 数据流

```
settings.yaml (provider: "fake")
    │
    ▼
LLMSettings(provider="fake", model="fake-model")
    │
    ▼
LLMFactory.create(settings)
    │  1. provider.lower().strip() → "fake"
    │  2. _PROVIDERS["fake"] → FakeLLM
    │  3. FakeLLM(settings) → 实例
    ▼
llm: BaseLLM = FakeLLM 实例
    │
    ▼
llm.chat([{"role": "user", "content": "hello"}]) → "fake response"
```

### 9.5 核心设计模式详解

**1. ABC（抽象基类）— 编译期约束**

```python
class BaseLLM(ABC):
    @abstractmethod
    def chat(self, messages, **kwargs) -> str: ...
# 忘记实现 chat() → TypeError: Can't instantiate abstract class
```

**2. 简单工厂模式 — 配置驱动创建**

```python
_PROVIDERS = {"fake": FakeLLM}  # 映射表代替 if/elif
LLMFactory.register("openai", OpenAILLM)  # 新增 Provider 不改 create()
```

**3. 测试桩（Test Stub）— 隔离外部依赖**

```python
# 真实 API：网络请求 + 费用 + 不稳定
# FakeLLM：本地 + 免费 + 确定性输出
```

**4. 异常转译模式**

```python
# openai.APIConnectionError → LLMError
# azure.AuthenticationError → LLMError
# 上层只需 except LLMError
```

### 9.6 messages 格式详解

```python
messages = [
    {"role": "system", "content": "你是 RAG 助手"},      # 系统提示词
    {"role": "user", "content": "什么是向量数据库？"},     # 用户输入
    {"role": "assistant", "content": "向量数据库是..."},   # AI 回复
    {"role": "user", "content": "有什么优势？"},          # 追问
]
# 所有 Provider 都兼容此 OpenAI Chat Completion API 标准格式
```

### 9.7 Bug 修复记录

**Bug：register 测试中自定义 LLM 类的 `__init__` 不接受 settings 参数**

- **现象**：`TypeError: CustomLLM() takes no arguments`
- **根因**：`LLMFactory.create()` 统一调用 `llm_class(settings)`，测试中的 CustomLLM 没定义 `__init__(self, settings)`
- **修复**：所有通过工厂创建的 BaseLLM 子类必须接受 `settings: LLMSettings` 参数
- **设计约束**：工厂模式的隐式契约 — 所有实现类的构造函数签名必须一致

### 9.8 测试覆盖

| 测试类 | 用例数 | 覆盖场景 |
|--------|--------|---------|
| `TestBaseLLMAbstract` | 4 | ABC 不能实例化、缺 chat/缺 model_name/完整实现 |
| `TestFakeLLM` | 6 | 默认回复、自定义回复、model_name、isinstance、忽略 messages |
| `TestLLMFactoryRouting` | 7 | fake 路由、chat 可用、不支持的 provider、大小写、空格、空字符串 |
| `TestLLMFactoryRegister` | 3 | 注册自定义 Provider、非 BaseLLM 子类报错、覆盖已有实现 |

### 9.9 修改文件清单

| 文件 | 变更 |
|------|------|
| `src/libs/llm/base_llm.py` | **新增**：BaseLLM 抽象基类 + LLMError + MessageType |
| `src/libs/llm/llm_factory.py` | **新增**：FakeLLM 测试桩 + LLMFactory 工厂 |
| `tests/unit/test_llm_factory.py` | **新增**：20 个测试用例 |

### 9.10 B1 面试高频问题

| 问题 | 关键答案 |
|------|---------|
| "ABC 的作用？" | 编译期约束 + 类型安全 + 接口契约，忘记实现会 TypeError |
| "简单工厂 vs 工厂方法？" | 产品少用简单工厂，多用工厂方法；本项目用映射表实现简单工厂 |
| "FakeLLM 和 MockLLM 的区别？" | Fake 返回固定值（测试桩）；Mock 记录调用并验证（模拟对象） |
| "工厂模式的好处？" | 改配置不改代码 + 上层只依赖接口 + 新增 Provider 不改工厂 |
| "什么是异常转译模式？" | 将底层异常包装为领域异常，上层代码不依赖底层异常类型 |
| "YAGNI 原则？" | You Aren't Gonna Need It，不要提前设计不需要的功能 |
| "开放-封闭原则？" | 对扩展开放（register 新 Provider），对修改封闭（不改 create） |
| "新增 LLM Provider 需要改什么？" | 1.实现 BaseLLM 子类 2.在 _PROVIDERS 注册 或 调用 register() |

---

## 10. B2：Embedding 抽象接口与工厂

### 10.1 目标

定义 `BaseEmbedding` 与 `EmbeddingFactory`，支持批量 embed。用 Fake provider 验证工厂路由逻辑。

### 10.2 关键设计决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 抽象基类 | ABC + @abstractmethod | 编译期约束子类必须实现 embed()、model_name、dimensions |
| 工厂模式 | 简单工厂（映射表） | Provider 数量少，映射表够用，与 B1 LLM 工厂保持一致 |
| 测试策略 | FakeEmbedding 测试桩 | 隔离测试，不依赖真实 API，稳定可重复 |
| embed() 入参 | list[str] 而非单个 str | 批量处理是 Embedding 的核心优化，减少 API 调用次数 |
| embed() 返回值 | list[list[float]] | 标准向量格式，与 NumPy / ChromaDB 等兼容 |
| FakeEmbedding 向量生成 | SHA256 哈希 → 确定性向量 | 相同文本 → 相同向量（可重复测试），不同文本 → 不同向量 |
| Provider 注册 | register() 方法 | 开放-封闭原则（OCP），与 B1 LLMFactory 一致 |
| dimensions 属性 | @property + @abstractmethod | 编译期约束子类必须暴露维度，用于校验与日志 |

### 10.3 关键接口签名（面试必须掌握）

```python
# ---- 抽象基类 ----
class BaseEmbedding(ABC):
    @abstractmethod
    def embed(self, texts: list[str], **kwargs) -> list[list[float]]
        # 入参：texts=["什么是向量数据库？", "RAG 是什么？"]
        # 出参：向量列表，每个向量是 list[float]，维度由模型决定
        # 异常：EmbeddingError

    @property
    @abstractmethod
    def model_name(self) -> str
        # 返回当前模型名称，用于日志和追踪

    @property
    @abstractmethod
    def dimensions(self) -> int
        # 返回向量维度（如 text-embedding-3-small = 1536）
        # 维度必须与向量数据库 collection 配置一致

# ---- 工厂 ----
class EmbeddingFactory:
    @classmethod
    def create(cls, settings: EmbeddingSettings) -> BaseEmbedding
        # provider → _PROVIDERS 映射表 → embedding_class(settings)

    @classmethod
    def register(cls, provider: str, embedding_class: type[BaseEmbedding]) -> None
        # 注册新 Provider，实现开放-封闭原则

# ---- 测试桩 ----
class FakeEmbedding(BaseEmbedding):
    def __init__(self, settings: EmbeddingSettings)
    def embed(texts, **kwargs) -> list[list[float]]  # SHA256 哈希生成确定性向量
```

### 10.4 数据流

```
settings.yaml (provider: "fake")
    │
    ▼
EmbeddingSettings(provider="fake", model="fake-model", dimensions=128)
    │
    ▼
EmbeddingFactory.create(settings)
    │  1. provider.lower().strip() → "fake"
    │  2. _PROVIDERS["fake"] → FakeEmbedding
    │  3. FakeEmbedding(settings) → 实例
    ▼
embedding: BaseEmbedding = FakeEmbedding 实例
    │
    ▼
embedding.embed(["hello", "world"])
    │  1. 对每个文本取 SHA256 哈希
    │  2. 哈希字节 → 归一化到 [-1, 1] 浮点数
    │  3. 截断/填充到 dimensions 维度
    ▼
[[0.01, -0.03, ...], [0.05, 0.02, ...]]  # 2 个向量，每个 128 维
```

### 10.5 核心设计模式详解

**1. ABC（抽象基类）— 编译期约束**

```python
class BaseEmbedding(ABC):
    @abstractmethod
    def embed(self, texts, **kwargs) -> list[list[float]]: ...
# 忘记实现 embed() → TypeError: Can't instantiate abstract class
```

与 B1 的 BaseLLM 完全一致的设计模式，三个抽象方法：`embed()`、`model_name`、`dimensions`。

**2. 简单工厂模式 — 配置驱动创建**

```python
_PROVIDERS = {"fake": FakeEmbedding}  # 映射表代替 if/elif
EmbeddingFactory.register("openai", OpenAIEmbedding)  # 新增 Provider 不改 create()
```

**3. 测试桩（Test Stub）— 隔离外部依赖**

```python
# 真实 API：网络请求 + 费用 + 不稳定
# FakeEmbedding：本地 + 免费 + 确定性输出（SHA256 哈希）
```

FakeEmbedding 与 FakeLLM 的区别：FakeLLM 返回固定字符串；FakeEmbedding 基于文本内容生成不同的确定性向量。

**4. 异常转译模式**

```python
# openai.APIConnectionError → EmbeddingError
# azure.AuthenticationError → EmbeddingError
# 上层只需 except EmbeddingError
```

### 10.6 Embedding 核心知识点详解

**1. Embedding 是什么？**

Embedding 是将文本映射为高维浮点向量的过程。语义相近的文本在向量空间中距离更近，这是 Dense Retrieval（稠密检索）的基础。

- 输入：`"什么是向量数据库？"`（字符串）
- 输出：`[0.012, -0.034, 0.056, ..., 0.078]`（1536 维浮点向量）
- 核心：语义相似的文本 → 向量距离近（cosine similarity 高）

**2. 为什么要批量 embed？**

| 方式 | API 调用次数 | 网络开销 | 成本 |
|------|------------|---------|------|
| 逐条 embed | N 次 | N 次网络往返 | 高 |
| 批量 embed | 1 次（或 N/batch_size 次） | 1 次网络往返 | 低 |

OpenAI / Azure / Ollama 等 API 都原生支持批量 embed，一次请求最多处理 2048 个文本（OpenAI 限制）。

**3. dimensions 为什么重要？**

不同 Embedding 模型输出维度不同：
- `text-embedding-3-small`：1536 维
- `text-embedding-3-large`：3072 维
- `text-embedding-ada-002`：1536 维
- Ollama `nomic-embed-text`：768 维

向量维度必须与向量数据库的 collection 配置一致，否则写入或检索会失败。

**4. 向量值域与归一化**

真实 Embedding 模型输出的向量值通常在 [-1, 1] 范围内，并经过 L2 归一化（向量的模长为 1）。FakeEmbedding 模拟了这个行为，将 SHA256 哈希字节映射到 [-1, 1] 区间。

**5. 稠密向量 vs 稀疏向量**

| 类型 | 生成方式 | 特点 | 适用场景 |
|------|---------|------|---------|
| 稠密向量 (Dense) | Embedding 模型（OpenAI/BGE） | 高维浮点（1536维），捕获语义 | 语义检索（同义词、模糊表达） |
| 稀疏向量 (Sparse) | BM25 / SPLADE | 关键词权重向量，大部分维度为 0 | 精确匹配（专有名词） |

本项目采用双路编码（Dense + Sparse），在检索阶段通过 RRF 融合两路结果。

### 10.7 FakeEmbedding 确定性向量生成策略

```python
# 1. 对文本取 SHA256 哈希 → 32 字节确定性序列
hash_bytes = hashlib.sha256(text.encode("utf-8")).digest()

# 2. 字节映射为浮点数，归一化到 [-1, 1]
# 每个 byte (0-255) → (byte - 128) / 128.0 → [-1, 1)
raw_floats = [(b - 128) / 128.0 for b in hash_bytes]

# 3. 扩展或截断到目标维度
# SHA256 只有 32 字节，如果 dimensions=1536，需要循环填充
if len(raw_floats) >= dimensions:
    vector = raw_floats[:dimensions]
else:
    vector = (raw_floats * (dimensions // len(raw_floats) + 1))[:dimensions]
```

为什么用 SHA256 而不是随机数？
- **确定性**：相同文本 → 相同向量，测试可重复
- **区分性**：不同文本 → 不同向量（哈希碰撞概率极低）
- **零依赖**：Python 标准库 hashlib，不需要额外安装

### 10.8 与 B1 (BaseLLM) 的设计对比

| 对比维度 | BaseLLM (B1) | BaseEmbedding (B2) |
|---------|-------------|-------------------|
| 核心方法 | `chat(messages) -> str` | `embed(texts) -> list[list[float]]` |
| 入参 | `list[dict]`（消息列表） | `list[str]`（文本列表） |
| 返回值 | `str`（文本） | `list[list[float]]`（向量列表） |
| 只读属性 | `model_name` | `model_name` + `dimensions` |
| 测试桩 | FakeLLM（返回固定字符串） | FakeEmbedding（返回确定性向量） |
| 异常类型 | LLMError | EmbeddingError |
| 工厂类 | LLMFactory | EmbeddingFactory |
| 设计模式 | ABC + 简单工厂 + register | ABC + 简单工厂 + register（完全一致） |

相同点：ABC 约束、简单工厂映射表、register() 开放-封闭、异常转译、Fake 测试桩
不同点：Embedding 多了 `dimensions` 属性（因为向量维度是关键约束）；FakeEmbedding 需要生成向量而非固定字符串

### 10.9 测试覆盖

| 测试类 | 用例数 | 覆盖场景 |
|--------|--------|---------|
| `TestBaseEmbeddingAbstract` | 5 | ABC 不能实例化、缺 embed/model_name/dimensions/完整实现 |
| `TestFakeEmbedding` | 14 | 返回向量、维度正确、确定性、不同文本不同向量、空列表、批量、值域范围、高维度填充、model_name、dimensions 属性 |
| `TestEmbeddingFactoryRouting` | 7 | fake 路由、embed 可用、不支持 provider、错误信息、大小写、空格、空字符串 |
| `TestEmbeddingFactoryRegister` | 3 | 注册自定义 Provider、非 BaseEmbedding 子类报错、覆盖已有实现 |

### 10.10 修改文件清单

| 文件 | 变更 |
|------|------|
| `src/libs/embedding/base_embedding.py` | **新增**：BaseEmbedding 抽象基类 + EmbeddingError |
| `src/libs/embedding/embedding_factory.py` | **新增**：FakeEmbedding 测试桩 + EmbeddingFactory 工厂 |
| `src/libs/embedding/__init__.py` | **更新**：导出 BaseEmbedding / EmbeddingError / EmbeddingFactory / FakeEmbedding |
| `tests/unit/test_embedding_factory.py` | **新增**：29 个测试用例 |

### 10.11 B2 面试高频问题

| 问题 | 关键答案 |
|------|---------|
| "Embedding 的作用？" | 将文本转为高维向量，使语义相似的文本距离更近，是稠密检索的基础 |
| "为什么要批量 embed？" | 减少 API 调用次数，降低成本和延迟，OpenAI 单次最多 2048 个文本 |
| "text-embedding-3-small 的维度？" | 1536 维 |
| "dimensions 不匹配会怎样？" | 向量写入或检索失败，维度必须与 collection 配置一致 |
| "稠密向量和稀疏向量区别？" | 稠密是高维浮点捕获语义；稀疏是关键词权重捕获精确匹配 |
| "FakeEmbedding 为什么用 SHA256？" | 确定性（相同文本→相同向量）+ 区分性（不同文本→不同向量）+ 零依赖 |
| "BaseEmbedding 和 BaseLLM 的设计区别？" | Embedding 多了 dimensions 属性；FakeEmbedding 生成向量而非返回固定字符串 |
| "embed() 为什么接受 list 而非单个 str？" | 批量处理是 Embedding 的核心优化策略，减少网络开销 |
| "向量值为什么要归一化？" | 使 cosine similarity 计算更稳定，不同向量的量级一致 |
| "新增 Embedding Provider 需要改什么？" | 1.实现 BaseEmbedding 子类 2.在 _PROVIDERS 注册 或 调用 register() |

---

## 11. B3：Splitter 抽象接口与工厂

### 11.1 目标

定义 `BaseSplitter` 与 `SplitterFactory`，支持不同切分策略（Recursive/Semantic/Fixed）。用 Fake provider 验证工厂路由逻辑。

### 11.2 关键设计决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 抽象基类 | ABC + @abstractmethod | 编译期约束子类必须实现 split_text() 和 provider_name |
| 工厂模式 | 简单工厂（映射表） | 与 B1/B2 保持一致，Provider 数量少，映射表够用 |
| 测试策略 | FakeSplitter 测试桩 | 隔离测试，不依赖 LangChain 等外部库 |
| split_text() 入参 | `str` 而非文件路径 | 单一职责：Splitter 只负责切分文本，文件读取由 Loader 负责 |
| split_text() 返回值 | `list[str]` | 纯文本输入输出，不涉及业务对象（Document/Chunk 转换由 C4 DocumentChunker 负责） |
| FakeSplitter 切分策略 | 定长切分 + 重叠 | 简化实现，按 chunk_size 切分，chunk_overlap 保留上下文 |
| SplitterSettings 新增 | 添加到 Settings dataclass 树 | 配置驱动 chunk_size / chunk_overlap / provider / separators |
| Provider 注册 | register() 方法 | 开放-封闭原则（OCP），与 B1/B2 工厂一致 |

### 11.3 关键接口签名（面试必须掌握）

```python
# ---- 抽象基类 ----
class BaseSplitter(ABC):
    @abstractmethod
    def split_text(self, text: str, **kwargs) -> list[str]
        # 入参：text = 原始文本（如 Markdown 文档全文）
        # 出参：切分后的文本片段列表（Chunk 列表）
        # 异常：SplitterError

    @property
    @abstractmethod
    def provider_name(self) -> str
        # 返回当前切分策略名称（'recursive' / 'semantic' / 'fixed' / 'fake'）

# ---- 工厂 ----
class SplitterFactory:
    @classmethod
    def create(cls, settings: SplitterSettings) -> BaseSplitter
        # provider → _PROVIDERS 映射表 → splitter_class(settings)

    @classmethod
    def register(cls, provider: str, splitter_class: type[BaseSplitter]) -> None
        # 注册新策略，实现开放-封闭原则

# ---- 测试桩 ----
class FakeSplitter(BaseSplitter):
    def __init__(self, settings: SplitterSettings)
    def split_text(text, **kwargs) -> list[str]  # 定长切分 + 重叠

# ---- 配置 ----
@dataclass
class SplitterSettings:
    provider: str = "recursive"        # 切分策略类型
    chunk_size: int = 1000             # 每个 Chunk 的最大字符数
    chunk_overlap: int = 200           # 相邻 Chunk 的重叠字符数
    separators: list[str] = ["\\n\\n", "\\n", " ", ""]  # 分隔符层级（Recursive 用）
```

### 11.4 数据流

```
settings.yaml (splitter.provider: "fake")
    │
    ▼
SplitterSettings(provider="fake", chunk_size=1000, chunk_overlap=200)
    │
    ▼
SplitterFactory.create(settings)
    │  1. provider.lower().strip() → "fake"
    │  2. _PROVIDERS["fake"] → FakeSplitter
    │  3. FakeSplitter(settings) → 实例
    ▼
splitter: BaseSplitter = FakeSplitter 实例
    │
    ▼
splitter.split_text("# 标题\n\n第一段...\n\n第二段...")
    │  1. step = chunk_size - chunk_overlap = 1000 - 200 = 800
    │  2. 按 step 步长滑动窗口切分
    │  3. 每个 chunk 最多 chunk_size 字符
    │  4. 相邻 chunk 有 chunk_overlap 字符的重叠
    ▼
["# 标题\n\n第一段...", "段...\n\n第二段..."]  # 2 个 chunk，有重叠
```

### 11.5 核心设计模式详解

**1. ABC（抽象基类）— 编译期约束**

```python
class BaseSplitter(ABC):
    @abstractmethod
    def split_text(self, text, **kwargs) -> list[str]: ...
# 忘记实现 split_text() → TypeError: Can't instantiate abstract class
```

与 B1 BaseLLM、B2 BaseEmbedding 完全一致的设计模式。

**2. 简单工厂模式 — 配置驱动创建**

```python
_PROVIDERS = {"fake": FakeSplitter}  # 映射表代替 if/elif
SplitterFactory.register("recursive", RecursiveSplitter)  # 新增策略不改 create()
```

**3. 测试桩（Test Stub）— 隔离外部依赖**

```python
# 真实 RecursiveSplitter：依赖 LangChain text-splitters 库
# FakeSplitter：纯 Python 标准库实现，零外部依赖
```

**4. 异常转译模式**

```python
# LangChain SplitTextError → SplitterError
# 上层只需 except SplitterError
```

### 11.6 Splitter 核心知识点详解

**1. 为什么要切分（Chunking）？**

| 原因 | 说明 |
|------|------|
| LLM 上下文有限 | GPT-4o 上下文 128K tokens，长文档超出限制 |
| Embedding 有最大输入长度 | OpenAI text-embedding-3-small 最多 8192 tokens |
| 检索粒度需要控制 | 整篇文档作为检索单元太粗，需要切分为语义单元 |
| 成本优化 | 短文本 Embedding 成本更低 |

**2. chunk_size 和 chunk_overlap 的作用**

```python
# chunk_size = 每个 Chunk 的最大字符数
# chunk_overlap = 相邻 Chunk 之间的重叠字符数

# 示例：text = "abcdefghij" (10 字符)
# chunk_size=4, chunk_overlap=2
# step = chunk_size - chunk_overlap = 2
# 切分结果: ["abcd", "cdef", "efgh", "ghij", "ij"]
#           ↑重叠↑  ↑重叠↑  ↑重叠↑  ↑重叠↑
```

**为什么要重叠？**
- 语义连续性：如果关键信息恰好在切分边界，重叠保证它同时出现在两个 chunk 中
- 检索质量：查询时能从相邻 chunk 获取更多上下文
- 典型值：chunk_size=1000, chunk_overlap=200（重叠 20%）

**3. 常见切分策略对比**

| 策略 | 原理 | 优点 | 缺点 | 适用场景 |
|------|------|------|------|---------|
| 固定长度 | 按字符数机械切分 | 实现最简单 | 可能切断语义 | 快速原型 |
| 递归字符 | 按分隔符层级（段落→句子→字符）递归切分 | 保持语义边界 | 需要配置分隔符 | Markdown/结构化文档（本项目默认） |
| 语义切分 | 用 Embedding 相似度检测语义断点 | 语义完整性最好 | 需要 Embedding API，成本高 | 高质量检索场景 |
| 结构感知 | 按文档结构（标题/代码块/列表）切分 | 保持文档结构 | 需要解析文档结构 | 代码/技术文档 |

**4. 职责边界：libs.splitter vs DocumentChunker（C4）**

| 组件 | 输入 | 输出 | 职责 |
|------|------|------|------|
| `libs.splitter` | `str` | `list[str]` | 纯文本切分，不涉及业务对象 |
| `DocumentChunker` (C4) | `Document` 对象 | `list[Chunk]` 对象 | 业务适配器，添加 Chunk ID、元数据继承、图片分发等 |

这种分离遵循**单一职责原则（SRP）**：libs.splitter 只管切文本，DocumentChunker 管业务对象转换。

### 11.7 FakeSplitter 切分算法详解

```python
def split_text(self, text: str) -> list[str]:
    if not text:
        return []

    # step = 每次前进的字符数
    # overlap >= chunk_size 时 step <= 0，会导致死循环
    # 此时退化为无重叠切分（step = chunk_size）
    step = self._chunk_size - self._chunk_overlap
    if step <= 0:
        step = self._chunk_size

    chunks = []
    start = 0
    while start < len(text):
        end = start + self._chunk_size
        chunk = text[start:end]    # Python 切片自动处理越界
        chunks.append(chunk)
        start += step              # 前进 step 步

    return chunks
```

**边界处理**：
- 空字符串 → 返回空列表
- 短文本（≤ chunk_size）→ 返回单元素列表
- overlap >= chunk_size → 退化为无重叠切分（防止死循环）
- chunk_overlap < 0 → 使用默认值 200

### 11.8 与 B1 (BaseLLM) / B2 (BaseEmbedding) 的设计对比

| 对比维度 | BaseLLM (B1) | BaseEmbedding (B2) | BaseSplitter (B3) |
|---------|-------------|-------------------|-------------------|
| 核心方法 | `chat(messages) -> str` | `embed(texts) -> list[list[float]]` | `split_text(text) -> list[str]` |
| 入参 | `list[dict]`（消息列表） | `list[str]`（文本列表） | `str`（单个文本） |
| 返回值 | `str`（文本） | `list[list[float]]`（向量矩阵） | `list[str]`（文本片段列表） |
| 只读属性 | `model_name` | `model_name` + `dimensions` | `provider_name` |
| 测试桩 | FakeLLM（返回固定字符串） | FakeEmbedding（SHA256 确定性向量） | FakeSplitter（定长切分+重叠） |
| 异常类型 | LLMError | EmbeddingError | SplitterError |
| 配置类 | LLMSettings | EmbeddingSettings | SplitterSettings（B3 新增） |
| 设计模式 | ABC + 简单工厂 + register | ABC + 简单工厂 + register | ABC + 简单工厂 + register（完全一致） |

**关键差异**：
- LLM/Embedding 的属性叫 `model_name`（因为它们对接模型）；Splitter 的属性叫 `provider_name`（因为它是策略而非模型）
- Splitter 是纯文本输入输出（`str → list[str]`），不涉及向量或 API 调用
- FakeSplitter 最简单：不需要哈希或固定字符串，只是按字符位置切分

### 11.9 SplitterSettings 配置详解

B3 阶段新增 `SplitterSettings` 到 `settings.py`：

```python
@dataclass
class SplitterSettings:
    provider: str = "recursive"       # 切分策略类型
    chunk_size: int = 1000            # 每个 Chunk 的最大字符数
    chunk_overlap: int = 200          # 相邻 Chunk 的重叠字符数
    separators: List[str] = field(default_factory=lambda: ["\n\n", "\n", " ", ""])
```

对应 YAML 配置：

```yaml
splitter:
  provider: recursive        # recursive / semantic / fixed / fake
  chunk_size: 1000           # 每个 Chunk 的最大字符数
  chunk_overlap: 200         # 相邻 Chunk 的重叠字符数
  separators:                # 递归切分的分隔符层级（从粗到细）
    - "\n\n"                 # 段落分隔
    - "\n"                   # 行分隔
    - " "                    # 词分隔
    - ""                     # 字符分隔（最后兜底）
```

**separators 的作用**（Recursive Splitter 用，B7.5 实现）：
- 切分时按分隔符层级递归尝试：先按段落切 → 太长则按行切 → 再按词切 → 最后按字符切
- 保证在 chunk_size 限制内尽量保持语义边界

### 11.10 测试覆盖

| 测试类 | 用例数 | 覆盖场景 |
|--------|--------|---------|
| `TestBaseSplitterAbstract` | 4 | ABC 不能实例化、缺 split_text/provider_name/完整实现 |
| `TestFakeSplitter` | 13 | 短文本、长文本、重叠切分、上下文连续性、空字符串、整数倍、默认值、负值修正、overlap>=chunk_size 退化、provider_name、isinstance、内容完整性、单字符 |
| `TestSplitterFactoryRouting` | 7 | fake 路由、split 可用、不支持 provider、错误信息、大小写、空格、空字符串 |
| `TestSplitterFactoryRegister` | 3 | 注册自定义 Provider、非 BaseSplitter 子类报错、覆盖已有实现 |

### 11.11 修改文件清单

| 文件 | 变更 |
|------|------|
| `src/core/settings.py` | **更新**：新增 SplitterSettings dataclass + Settings 字段 + _FIELD_TYPE_MAP 映射 |
| `src/libs/splitter/base_splitter.py` | **新增**：BaseSplitter 抽象基类 + SplitterError |
| `src/libs/splitter/splitter_factory.py` | **新增**：FakeSplitter 测试桩 + SplitterFactory 工厂 |
| `src/libs/splitter/__init__.py` | **更新**：导出 BaseSplitter / SplitterError / SplitterFactory / FakeSplitter |
| `tests/unit/test_splitter_factory.py` | **新增**：27 个测试用例 |

### 11.12 B3 面试高频问题

| 问题 | 关键答案 |
|------|---------|
| "为什么要切分文档？" | LLM 上下文有限 + Embedding 有最大输入长度 + 检索粒度需要控制 + 成本优化 |
| "chunk_size 和 chunk_overlap 的作用？" | chunk_size 控制每个片段最大长度；chunk_overlap 保留相邻片段的上下文连续性 |
| "为什么要重叠？" | 防止关键信息被切断，保证语义连续性，典型值 chunk_size=1000 overlap=200（20%） |
| "常见的切分策略？" | 固定长度 / 递归字符 / 语义切分 / 结构感知，本项目默认用 Recursive |
| "split_text 为什么接受 str 而非文件路径？" | 单一职责原则，Splitter 只负责切分文本，文件读取由 Loader 负责 |
| "libs.splitter 和 DocumentChunker 的区别？" | libs.splitter 是纯文本切分（str→list[str]）；DocumentChunker 是业务适配器（Document→list[Chunk]） |
| "FakeSplitter 和 RecursiveSplitter 的区别？" | Fake 按字符位置机械切分；Recursive 按分隔符层级递归切分，保持语义边界 |
| "overlap >= chunk_size 会怎样？" | 退化为无重叠切分（step=chunk_size），防止死循环 |
| "为什么 Splitter 属性叫 provider_name 而非 model_name？" | Splitter 是策略而非模型，不涉及 AI 模型调用 |
| "新增切分策略需要改什么？" | 1.实现 BaseSplitter 子类 2.在 _PROVIDERS 注册 或 调用 register() |
| "separators 的作用？" | 递归切分的分隔符层级，从粗到细尝试（段落→行→词→字符），在长度限制内保持语义边界 |

---

## 12. B4：VectorStore 抽象接口与工厂（先定义契约）

### 12.1 目标

定义 `BaseVectorStore` 与 `VectorStoreFactory`，先不接真实 DB。用 FakeVectorStore 验证接口契约（输入输出 shape）。

### 12.2 关键设计决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 抽象基类 | ABC + @abstractmethod | 编译期约束子类必须实现 5 个核心方法 |
| 工厂模式 | 简单工厂（映射表） | 与 B1/B2/B3 保持一致，后端数量少 |
| 测试策略 | FakeVectorStore 测试桩 | 纯内存存储 + cosine similarity 纯 Python 计算 |
| 接口完整度 | 一次定义 5 个方法 | upsert/query/delete/get_by_ids/delete_by_metadata，覆盖后续 C12/D2/D3/G2 全部需求 |
| 数据契约 | VectorRecord + QueryResult | 用 dataclass 定义输入输出类型，类型安全 + IDE 补全 |
| 幂等 upsert | dict 存储，key=id | 相同 id 覆盖旧记录，不产生重复 |
| 查询算法 | cosine similarity | 不受向量长度影响，只关注方向 |
| metadata 过滤 | AND 逻辑 | filter 中所有 key-value 对都必须精确匹配 |
| 测试类型 | 契约测试（Contract Test） | 不测业务逻辑，只测接口输入输出 shape 是否符合约定 |

### 12.3 关键接口签名（面试必须掌握）

```python
# ---- 数据契约 ----
@dataclass
class VectorRecord:
    id: str                         # 记录唯一标识（chunk_id）
    embedding: list[float]          # 向量
    text: str                       # 原始文本
    metadata: dict[str, Any]        # 元数据

@dataclass
class QueryResult:
    id: str                         # 记录 ID
    score: float                    # 相似度分数（cosine similarity）
    text: str                       # 匹配的文本
    metadata: dict[str, Any]        # 元数据

# ---- 抽象基类 ----
class BaseVectorStore(ABC):
    @abstractmethod
    def upsert(self, records: list[VectorRecord]) -> None
        # 幂等写入：相同 id 覆盖旧记录

    @abstractmethod
    def query(self, vector: list[float], top_k: int = 10,
              filters: dict | None = None) -> list[QueryResult]
        # 向量相似度检索，按 score 降序返回 top_k 条

    @abstractmethod
    def delete(self, ids: list[str]) -> int
        # 按 ID 删除，返回删除数量

    @abstractmethod
    def get_by_ids(self, ids: list[str]) -> list[dict]
        # 按 ID 批量获取（不含向量）

    @abstractmethod
    def delete_by_metadata(self, filter: dict) -> int
        # 按 metadata 批量删除

# ---- 工厂 ----
class VectorStoreFactory:
    @classmethod
    def create(cls, settings: VectorStoreSettings) -> BaseVectorStore
    @classmethod
    def register(cls, backend: str, store_class: type[BaseVectorStore]) -> None
```

### 12.4 数据流

```
---- Ingestion 阶段（写入）----
Chunk → Embedding → VectorRecord(id, embedding, text, metadata)
    │
    ▼
VectorStore.upsert([record1, record2, ...])
    │  幂等写入：相同 id 覆盖
    ▼
存储到向量数据库（Fake=内存dict / Chroma=本地文件）

---- Retrieval 阶段（查询）----
Query → Embedding → query_vector
    │
    ▼
VectorStore.query(query_vector, top_k=10, filters={"source": "doc.pdf"})
    │  1. 过滤：metadata 匹配
    │  2. 打分：cosine similarity
    │  3. 排序：score 降序
    │  4. 截断：取 top_k 条
    ▼
[QueryResult(id, score, text, metadata), ...]
```

### 12.5 核心设计模式详解

**1. ABC（抽象基类）— 编译期约束**

5 个抽象方法：`upsert` / `query` / `delete` / `get_by_ids` / `delete_by_metadata`，忘记实现任何一个都会 TypeError。

**2. 简单工厂模式 — 配置驱动创建**

```python
_BACKENDS = {"fake": FakeVectorStore}  # 映射表
VectorStoreFactory.register("chroma", ChromaStore)  # B7.6 注册
```

**3. 契约测试（Contract Testing）— 接口兼容性验证**

```python
# 契约测试不测逻辑，只测"形状"
assert isinstance(results, list)           # 返回类型是 list
assert all(isinstance(r, QueryResult) for r in results)  # 元素是 QueryResult
assert hasattr(r, "id")                    # 有 id 字段
assert hasattr(r, "score")                 # 有 score 字段
assert isinstance(r.score, float)          # score 是 float
```

**4. 幂等 upsert 模式**

```python
# dict 存储，key=id → 相同 id 自动覆盖
self._store[record.id] = record
```

### 12.6 VectorStore 核心知识点详解

**1. 向量数据库的作用**

| 功能 | 说明 |
|------|------|
| 存储 | 存储向量 + 原文 + metadata |
| 检索 | 给一个查询向量，返回最相似的 K 条记录 |
| 删除 | 按 ID 或 metadata 条件删除记录 |
| 相似度 | cosine similarity（夹角余弦值） |

**2. 为什么用 cosine similarity？**

```python
cos(A, B) = (A · B) / (||A|| * ||B||)
# A · B = sum(a_i * b_i)  — 点积
# ||A|| = sqrt(sum(a_i^2)) — 模长
# 值域 [-1, 1]，越接近 1 越相似
```

| 度量方式 | 公式 | 特点 |
|---------|------|------|
| Cosine Similarity | cos(θ) | 不受向量长度影响，只关注方向 |
| 欧氏距离 | √Σ(a-b)² | 受向量长度影响 |
| 点积 | Σa·b | 受向量长度影响，但计算最快 |

面试考点："为什么用 cosine？" → Embedding 向量通常已归一化（模长=1），此时 cosine = 点积，但 cosine 更通用。

**3. 幂等 upsert 与 ID 生成策略**

```python
# ID 生成策略（C12 VectorUpserter 实现）
chunk_id = hash(source_path + chunk_index + content_hash[:8])

# 幂等性保证：
# - 内容不变 → content_hash 不变 → id 不变 → upsert 覆盖（幂等）
# - 内容变更 → content_hash 变化 → id 变化 → 新记录
# - 文件名变更但内容不变 → content_hash 不变 → id 不变 → 复用（增量优化）
```

**4. metadata 过滤的作用**

```python
# 查询时只返回特定文档的 chunk
store.query(vector, top_k=10, filters={"source_path": "doc.pdf"})

# 多条件 AND 过滤
store.query(vector, top_k=10, filters={"source": "doc.pdf", "page": 1})
```

应用场景：
- 按文档过滤检索范围
- 按页面/章节缩小检索
- DocumentManager 按条件批量删除

**5. 五个接口方法的用途与使用阶段**

| 方法 | 用途 | 使用阶段 |
|------|------|---------|
| `upsert` | 写入/更新向量 | C12 (VectorUpserter) |
| `query` | 向量相似度检索 | D2 (DenseRetriever) |
| `delete` | 按 ID 删除 | G2 (DocumentManager) |
| `get_by_ids` | 按 ID 获取原文 | D3 (SparseRetriever) |
| `delete_by_metadata` | 按 metadata 批量删除 | G2 (DocumentManager) |

### 12.7 契约测试 vs 单元测试

| 维度 | 契约测试 | 单元测试 |
|------|---------|---------|
| 目的 | 验证接口输入输出 shape | 验证业务逻辑正确性 |
| 关注点 | 类型对不对、字段全不全 | 结果对不对、排序对不对 |
| 示例 | `assert isinstance(r, QueryResult)` | `assert r.score == 1.0` |
| 价值 | 保证不同实现兼容同一接口 | 保证实现逻辑正确 |

B4 的测试同时包含契约测试和单元测试：契约测试验证 VectorRecord/QueryResult 的字段，单元测试验证 cosine similarity 计算和幂等 upsert 逻辑。

### 12.8 与 B1/B2/B3 的设计对比

| 对比维度 | BaseLLM (B1) | BaseEmbedding (B2) | BaseSplitter (B3) | BaseVectorStore (B4) |
|---------|-------------|-------------------|-------------------|---------------------|
| 核心方法 | `chat()` | `embed()` | `split_text()` | `upsert()` + `query()` + `delete()` + `get_by_ids()` + `delete_by_metadata()` |
| 方法数量 | 1 | 1 | 1 | 5 |
| 入参 | `list[dict]` | `list[str]` | `str` | `list[VectorRecord]` / `list[float]` / `list[str]` / `dict` |
| 返回值 | `str` | `list[list[float]]` | `list[str]` | `None` / `list[QueryResult]` / `int` / `list[dict]` |
| 数据契约 | 无 | 无 | 无 | VectorRecord + QueryResult |
| 只读属性 | `model_name` | `model_name` + `dimensions` | `provider_name` | 无（工厂属性是 backend_name） |
| 测试桩 | FakeLLM（固定字符串） | FakeEmbedding（SHA256 向量） | FakeSplitter（定长切分） | FakeVectorStore（内存 dict + cosine） |
| 异常类型 | LLMError | EmbeddingError | SplitterError | VectorStoreError |
| 配置类 | LLMSettings | EmbeddingSettings | SplitterSettings | VectorStoreSettings |
| 测试类型 | 单元测试 | 单元测试 | 单元测试 | 契约测试 + 单元测试 |

**关键差异**：
- VectorStore 是四个组件中**接口最复杂**的（5 个方法 + 2 个数据类型）
- VectorStore 首次引入**数据契约**（VectorRecord / QueryResult），用 dataclass 明确输入输出 shape
- VectorStore 首次使用**契约测试**，验证接口兼容性
- FakeVectorStore 是最复杂的测试桩：需要实现 cosine similarity 计算

### 12.9 测试覆盖

| 测试类 | 用例数 | 覆盖场景 |
|--------|--------|---------|
| `TestBaseVectorStoreAbstract` | 4 | ABC 不能实例化、缺 upsert/query/完整实现 |
| `TestVectorRecordContract` | 4 | 必需字段、metadata 默认值、实例独立性、字段类型 |
| `TestQueryResultContract` | 3 | 必需字段、metadata 默认值、字段类型 |
| `TestFakeVectorStoreUpsertContract` | 4 | 单条/多条/幂等/空列表 |
| `TestFakeVectorStoreQueryContract` | 11 | 返回类型、字段完整、score 降序、top_k、空库、metadata 过滤、多条件、无匹配、score 值域、维度不匹配 |
| `TestFakeVectorStoreDeleteContract` | 4 | 删除存在/不存在/部分/空列表 |
| `TestFakeVectorStoreGetByIdsContract` | 5 | 返回 dict、字段完整、不含 embedding、不存在、部分匹配 |
| `TestFakeVectorStoreDeleteByMetadataContract` | 3 | 返回数量、无匹配、多条件 AND |
| `TestVectorStoreFactoryRouting` | 6 | fake 路由、可用、不支持、大小写、空格、空字符串 |
| `TestVectorStoreFactoryRegister` | 3 | 注册自定义/非子类报错/覆盖已有 |
| `TestCosineSimilarity` | 3 | 相同向量(1.0)/正交向量(0.0)/45度角(0.707) |

### 12.10 修改文件清单

| 文件 | 变更 |
|------|------|
| `src/libs/vector_store/base_vector_store.py` | **新增**：BaseVectorStore 抽象基类 + VectorRecord + QueryResult + VectorStoreError |
| `src/libs/vector_store/vector_store_factory.py` | **新增**：FakeVectorStore 测试桩（内存存储+cosine）+ VectorStoreFactory 工厂 |
| `src/libs/vector_store/__init__.py` | **更新**：导出 BaseVectorStore / VectorStoreError / VectorRecord / QueryResult / VectorStoreFactory / FakeVectorStore |
| `tests/unit/test_vector_store_contract.py` | **新增**：49 个测试用例（契约测试 + 单元测试） |

### 12.11 B4 面试高频问题

| 问题 | 关键答案 |
|------|---------|
| "VectorStore 的作用？" | 存储向量 + 语义检索（cosine similarity）+ 按 ID/metadata 删除 |
| "为什么用 Chroma？" | 嵌入式设计，pip install 即可，无需部署 Docker |
| "upsert 和 insert 的区别？" | upsert 幂等，相同 id 覆盖；insert 可能产生重复 |
| "cosine similarity 公式？" | cos(A,B) = (A·B) / (\|\|A\|\|·\|\|B\|\|)，值域 [-1,1] |
| "为什么用 cosine 而非欧氏距离？" | 不受向量长度影响，只关注方向 |
| "VectorRecord 包含哪些字段？" | id、embedding、text、metadata |
| "QueryResult 包含哪些字段？" | id、score、text、metadata |
| "get_by_ids 为什么不返回向量？" | 向量很大（1536维=6KB），批量返回浪费内存，调用方通常只需 text+metadata |
| "delete_by_metadata 的用途？" | DocumentManager 删除文档时按 source_path 批量删除所有关联 chunk |
| "什么是契约测试？" | 验证接口输入输出 shape（类型/字段），不测业务逻辑 |
| "metadata 过滤逻辑？" | AND 逻辑，filter 中所有 key-value 对都必须精确匹配 |
| "FakeVectorStore 如何计算相似度？" | 纯 Python 实现 cosine similarity，遍历所有记录计算点积和模长 |
| "新增向量数据库后端需要改什么？" | 1.实现 BaseVectorStore 5 个方法 2.在 _BACKENDS 注册 或 调用 register() |
| "维度不匹配时 cosine 怎么处理？" | 返回 0.0（不相似），避免数学错误 |

---

## 13. B5: Reranker 抽象接口与工厂

### 13.1 任务概述

**目标**：实现 `BaseReranker`、`RerankerFactory`，提供 `NoneReranker` 作为默认回退。

**修改文件**：
- `src/libs/reranker/base_reranker.py` — 抽象基类 + 数据契约
- `src/libs/reranker/reranker_factory.py` — 工厂 + NoneReranker 实现
- `src/libs/reranker/__init__.py` — 模块导出
- `tests/unit/test_reranker_factory.py` — 37 个测试用例

### 13.2 核心架构

```
BaseReranker (ABC)          ← 抽象基类，定义 rerank() 接口
├── NoneReranker            ← 默认回退（Null Object 模式），不重排
├── CrossEncoderReranker    ← B7.8 实现（CrossEncoder 精排）
└── LLMReranker             ← B7.7 实现（LLM 打分）

RerankerFactory             ← 工厂，根据 settings.rerank.backend 创建实例
├── enabled=False → NoneReranker  （降级，不报错）
├── backend="none" → NoneReranker
├── backend="cross_encoder" → CrossEncoderReranker (B7.8)
└── backend="llm" → LLMReranker (B7.7)
```

### 13.3 数据契约：RerankCandidate

```python
@dataclass
class RerankCandidate:
    id: str                                    # 候选记录 ID（chunk_id）
    score: float                               # 检索分数（粗排分数 → 精排分数）
    text: str                                  # 候选文本（送入 CrossEncoder/LLM）
    metadata: dict[str, Any] = field(...)      # 元数据（保留传递）
```

**设计要点**：
- `score` 字段在重排前后会变化（粗排 → 精排分数）
- `id`/`text`/`metadata` 不变，只是顺序变
- 与 D2 的 `RetrievalResult` 字段对齐，方便 Core 层转换

### 13.4 接口签名

```python
class BaseReranker(ABC):
    @abstractmethod
    def rerank(self, query: str, candidates: list[RerankCandidate], **kwargs) -> list[RerankCandidate]: ...

    @property
    @abstractmethod
    def backend_name(self) -> str: ...
```

### 13.5 关键设计决策

#### 1. Null Object 模式（NoneReranker）
- **问题**：Reranker 是可选组件，未启用或失败时怎么办？
- **方案**：用 `NoneReranker`（什么都不做的对象）代替 `None/null`
- **好处**：上层代码不需要判空，统一调用 `rerank()` 接口
- **对比**：如果返回 `None`，上层每次调用前都要 `if reranker is not None`

#### 2. enabled=False 优先于 backend 校验
- **问题**：`enabled=False` + `backend="cross_encoder"`（但 CrossEncoder 未实现）应该报错吗？
- **方案**：不报错，直接返回 `NoneReranker`
- **原因**：未启用时不关心 backend 是否有效，避免无意义的报错

#### 3. 防御性拷贝
- `NoneReranker.rerank()` 返回 `list(candidates)` 而非 `candidates`
- 避免外部修改影响内部状态

#### 4. 工厂与 B1-B4 的区别
- B1-B4 工厂：不支持的 provider 直接报错
- B5 工厂：`enabled=False` 时不报错，返回 `NoneReranker`（降级）
- 这是 Reranker 的特殊性：可选组件，不启用时系统仍需正常工作

### 13.6 两段式检索架构（面试重点）

```
用户查询
  │
  ▼
粗排（Coarse Ranking）— Hybrid Search
  ├── Dense Retrieval（向量检索）→ Bi-Encoder 分离编码
  ├── Sparse Retrieval（BM25 关键词）→ TF-IDF 倒排索引
  └── RRF Fusion（排名融合）→ Top-M 候选
  │
  ▼ Top-M candidates
精排（Fine Ranking）— Reranker
  ├── CrossEncoder：query + doc 联合编码，精度高但慢
  ├── LLM Rerank：让 LLM 对候选打分
  └── None：不重排（默认回退）
  │
  ▼ Top-K results
最终返回
```

**Bi-Encoder vs Cross-Encoder**：
| 特性 | Bi-Encoder（粗排） | Cross-Encoder（精排） |
|------|---------------------|----------------------|
| 编码方式 | query 和 doc 分离编码 | query 和 doc 联合编码 |
| 预计算 | doc 向量可预计算 | 无法预计算 |
| 速度 | 快（向量相似度） | 慢（每对都要推理） |
| 精度 | 一般 | 高 |
| 用途 | 从百万文档召回 Top-M | 从 Top-M 精选 Top-K |

### 13.7 测试覆盖

| 测试类别 | 数量 | 关键测试 |
|---------|------|---------|
| RerankCandidate 数据契约 | 6 | 字段定义、默认值、独立性、可变性、相等性 |
| BaseReranker ABC 契约 | 8 | 抽象类不可实例化、子类未实现→TypeError、完整子类可实例化 |
| NoneReranker 行为 | 10 | 不改变顺序/score/metadata/text、空列表、单候选、防御性拷贝 |
| RerankerFactory 工厂 | 9 | backend=none→NoneReranker、enabled=False→NoneReranker、未知backend→Error、大小写不敏感、register() |
| 端到端集成 | 3 | 完整流程：创建→rerank→验证 |
| **合计** | **37** | |

### 13.8 面试问答

| 问题 | 回答 |
|------|------|
| "为什么要 Rerank？" | 粗排用速度换覆盖率（BM25+Dense），精排用质量换速度（CrossEncoder） |
| "NoneReranker 的作用？" | 默认回退，Reranker 失败或未启用时保持原排序，保证系统可用性 |
| "Null Object 模式？" | 用空行为对象代替 null 检查，上层代码统一调用接口不需要判空 |
| "CrossEncoder vs Bi-Encoder？" | CrossEncoder 联合编码精度高但慢；Bi-Encoder 分离编码快但精度低 |
| "Reranker 未启用时工厂返回什么？" | NoneReranker（不是 None），让上层代码统一调用 rerank() |
| "rerank 会改变候选内容吗？" | 不会，只改变顺序和 score，id/text/metadata 不变 |
| "新增重排后端需要改什么？" | 1.实现 BaseReranker 的 rerank() 和 backend_name 2.在 _BACKENDS 注册或调用 register() |
| "enabled=False + 未知 backend 会报错吗？" | 不会，enabled=False 优先于 backend 校验，直接返回 NoneReranker |

---

## 14. B6: Evaluator 抽象接口与工厂

### 14.1 任务概述

**目标**：定义 `BaseEvaluator`、`EvaluatorFactory`，实现最小 `CustomEvaluator`（hit_rate/mrr/recall@k/precision@k）。

**修改文件**：
- `src/libs/evaluator/base_evaluator.py` — 抽象基类 + 数据契约
- `src/libs/evaluator/custom_evaluator.py` — 自定义轻量指标实现
- `src/libs/evaluator/evaluator_factory.py` — 工厂
- `src/libs/evaluator/__init__.py` — 模块导出
- `tests/unit/test_custom_evaluator.py` — 58 个测试用例

### 14.2 核心架构

```
BaseEvaluator (ABC)          ← 抽象基类，定义 evaluate() 接口
├── CustomEvaluator          ← 轻量检索指标（hit_rate, mrr, recall@k, precision@k）
├── RagasEvaluator           ← H1 阶段实现（LLM-as-Judge 生成指标）
└── CompositeEvaluator       ← H2 阶段实现（组合多后端并行）

EvaluatorFactory             ← 工厂，根据 backend 创建实例
├── backend="custom"  → CustomEvaluator
├── backend="ragas"   → RagasEvaluator (H1)
└── register() 支持动态注册
```

### 14.3 数据契约

```python
@dataclass
class RetrievedChunk:       # 检索结果单元（evaluate 的输入）
    id: str                 # chunk_id
    score: float            # 检索分数
    text: str               # 检索文本
    metadata: dict[str, Any]

@dataclass
class GroundTruth:          # 标准答案（evaluate 的输入）
    query: str              # 原始查询
    golden_ids: list[str]   # 正确 chunk_id 列表（用于检索评估）
    golden_answer: str      # 标准答案文本（用于生成评估）

@dataclass
class EvalResult:           # 评估结果（evaluate 的输出）
    backend_name: str       # 后端名称
    metrics: dict[str, float]  # 指标字典（灵活扩展）
    details: dict[str, Any]    # 详细信息
```

### 14.4 接口签名

```python
class BaseEvaluator(ABC):
    @abstractmethod
    def evaluate(self, query: str, retrieved_chunks: list[RetrievedChunk],
                 generated_answer: str, ground_truth: GroundTruth) -> EvalResult: ...

    @property
    @abstractmethod
    def backend_name(self) -> str: ...
```

### 14.5 检索质量指标定义（面试重点）

| 指标 | 定义 | 取值 | 公式 |
|------|------|------|------|
| Hit Rate | golden_id 是否在 Top-K 中 | 0 或 1 | `1 if len(set(top_k_ids) & golden_set) > 0 else 0` |
| MRR | 第一个命中的排名倒数 | 0~1 | `1 / rank_of_first_hit` |
| Recall@K | Top-K 中命中的 golden_ids 比例 | 0~1 | `hit_count / len(golden_ids)` |
| Precision@K | Top-K 中命中数 / K | 0~1 | `hit_count / K` |

**Hit Rate vs MRR**：
- Hit Rate 只判有无（0 或 1），不关心排名位置
- MRR 关心命中位置（第 1 名=1.0，第 3 名=0.333）

**Recall vs Precision**：
- Recall 看覆盖率（漏了多少 golden）
- Precision 看准确率（Top-K 中有多少正确的）

### 14.6 关键设计决策

#### 1. 标准化输出（EvalResult.metrics 是 dict）
- 不同评估后端的指标不同（custom 输出 hit_rate/mrr，ragas 输出 faithfulness）
- 用 dict 可以灵活扩展，不需要改 EvalResult 类
- 面试考点："为什么用 dict 而非固定字段？" → 可扩展性

#### 2. 工厂接受 backend 字符串而非 Settings 对象
- EvaluationSettings.backends 是 `List[str]`（多个后端）
- 需要逐个创建，所以工厂接受 backend 字符串
- 面试考点："为什么 B6 工厂不接受 Settings？" → backends 是列表

#### 3. evaluate 只评估单条查询
- 单一职责：evaluate 只负责一条查询的评估
- 批量评估在上层循环调用，然后取平均
- 面试考点："为什么不在 evaluate 里做批量？" → 单一职责

#### 4. generated_answer 在 CustomEvaluator 中不使用
- CustomEvaluator 只评估检索质量（hit_rate, mrr）
- generated_answer 和 golden_answer 在 RagasEvaluator 中才使用
- 面试考点："CustomEvaluator 用 generated_answer 吗？" → 不用，只评估检索

### 14.7 测试覆盖

| 测试类别 | 数量 | 关键测试 |
|---------|------|---------|
| RetrievedChunk 数据契约 | 5 | 字段定义、默认值、独立性、相等性 |
| GroundTruth 数据契约 | 5 | 字段定义、默认值、独立性 |
| EvalResult 数据契约 | 5 | 字段定义、默认值、独立性、相等性 |
| BaseEvaluator ABC 契约 | 8 | 抽象类不可实例化、子类未实现→TypeError |
| CustomEvaluator 指标 | 18 | hit_rate/mrr/recall/precision 各场景、边界情况、确定性 |
| EvaluatorFactory 工厂 | 9 | custom→CustomEvaluator、未知→Error、register()、大小写 |
| 端到端集成 | 4 | 完整流程、命中/未命中/多 golden、确定性验证 |
| **合计** | **58** | |

### 14.8 面试问答

| 问题 | 回答 |
|------|------|
| "Hit Rate 和 MRR 的区别？" | Hit Rate 只判有无，MRR 还看排名位置 |
| "MRR 为什么用倒数？" | 排名越靠前分数越高（第 1 名=1.0，第 3 名=0.333） |
| "Recall 和 Precision 的区别？" | Recall 看覆盖率（漏了多少），Precision 看准确率（错了多少） |
| "为什么用 CustomEvaluator 而非 Ragas？" | 轻量快速，不依赖 LLM，适合 CI/CD |
| "为什么 metrics 用 dict 而非固定字段？" → | 不同后端指标不同，dict 可灵活扩展 |
| "新增评估后端需要改什么？" | 1.实现 BaseEvaluator 的 evaluate() 和 backend_name 2.在 _BACKENDS 注册或调用 register() |
| "evaluate 方法评估单条还是批量？" | 单条，批量在上层循环调用取平均 |
| "golden_ids 为空怎么办？" | 抛出 EvaluatorError，没有标准答案无法评估 |

---

## 15. Stage B7 完成总结：具体 Provider 实现（B7.1-B7.8）

**完成时间**：2025-08-21
**测试总数**：391 全部通过（0.96s）

### 15.1 B7.1-B7.2: LLM Provider 实现

| 文件 | 代码行 | 测试数 | 关键设计 |
|------|--------|--------|---------|
| `openai_llm.py` | ~120 | 8 (smoke) | httpx 封装 OpenAI-compatible API，不依赖 openai SDK |
| `azure_llm.py` | ~130 | 8 (smoke) | httpx 封装 Azure OpenAI，api-version 参数 |
| `deepseek_llm.py` | ~110 | 9 (smoke) | 继承 OpenAI LLM，覆盖 base_url |
| `ollama_llm.py` | ~130 | 12 | httpx 封装 Ollama REST API /chat，options 传参 |

**核心设计决策**：
- 不依赖 `openai` SDK，用 `httpx` 直接封装 → 减少依赖、更可控
- 所有 LLM 继承 `BaseLLM`，实现 `chat()` + `model_name` property
- 测试用 `httpx.MockTransport` 确保不依赖外部网络

### 15.2 B7.3-B7.4: Embedding Provider 实现

| 文件 | 代码行 | 测试数 | 关键设计 |
|------|--------|--------|---------|
| `openai_embedding.py` | ~130 | 11 (smoke) | httpx 封装 /v1/embeddings，维度校验 |
| `azure_embedding.py` | ~130 | 8 (smoke) | Azure OpenAI deployment name 替代 model |
| `ollama_embedding.py` | ~120 | 14 | 循环单条调用 Ollama /api/embeddings |

**核心设计决策**：
- `embed()` 支持批量输入，统一返回 `list[list[float]]`
- 维度自动检测：`dimensions=0` 时不校验，由模型决定
- Ollama API 不支持批量 → 在 `embed()` 内循环单条调用

### 15.3 B7.5: Recursive Splitter 实现

| 文件 | 代码行 | 测试数 | 关键设计 |
|------|--------|--------|---------|
| `recursive_splitter.py` | ~200 | 18 | 纯 Python 递归字符切分，不依赖 LangChain |

**核心算法**：
1. 按分隔符层级递归切分：`\n\n` → `\n` → ` ` → 逐字符
2. 切分后片段超长 → 用下一级分隔符继续切
3. 合并相邻小片段到接近 `chunk_size`
4. 添加 `chunk_overlap` 重叠保持上下文连续性

**面试要点**：
- "Recursive 和定长切分的区别？" → 递归优先在分隔符处切，保持语义边界
- "为什么要递归？" → 尽量保持语义边界，只在必要时才往更细粒度切

### 15.4 B7.6: ChromaStore 实现

| 文件 | 代码行 | 测试数 | 关键设计 |
|------|--------|--------|---------|
| `chroma_store.py` | ~230 | 16 (integration) | ChromaDB PersistentClient，cosine 距离 |

**核心操作**：
- `upsert()` → 幂等写入（相同 ID 覆盖）
- `query()` → 向量相似度检索 + metadata 过滤
- `delete()` → 按 ID 删除
- `get_by_ids()` → 批量获取（不含向量）
- `delete_by_metadata()` → 按 metadata 条件批量删除

**面试要点**：
- "Chroma 和 Qdrant 的区别？" → Chroma 嵌入式无需部署，Qdrant 需要容器
- "upsert 和 insert 的区别？" → upsert 幂等，相同 ID 覆盖旧记录
- "Chroma 的 where 过滤？" → 支持 `$eq/$ne/$in` 等 metadata 操作符

### 15.5 B7.7: LLM Reranker 实现

| 文件 | 代码行 | 测试数 | 关键设计 |
|------|--------|--------|---------|
| `llm_reranker.py` | ~160 | 17 | LLM 打分 + 正则解析 + 失败回退 |

**核心流程**：
1. 读取 `config/prompts/rerank.txt` prompt 模板
2. 对每个候选构造 prompt（query + doc）→ 调用 LLM → 解析 1-10 评分
3. 按评分降序排列
4. LLM 调用失败时返回 0.0 分（不阻断流程）

**面试要点**：
- "LLM Rerank vs CrossEncoder？" → LLM 更灵活但慢
- "LLM 输出不规范怎么办？" → 正则提取数字 + 默认值
- "Reranker 失败怎么办？" → 返回原排序，不阻断流程

### 15.6 B7.8: Cross-Encoder Reranker 实现

| 文件 | 代码行 | 测试数 | 关键设计 |
|------|--------|--------|---------|
| `cross_encoder_reranker.py` | ~160 | 14 | scorer 依赖注入 + Jaccard 默认打分 |

**核心设计**：
- 使用可注入的 `scorer: Callable[[str, str], float]` 函数
- 默认 scorer 用 Jaccard 相似度（词汇重叠率）→ 确定性、不依赖外部模型
- 生产环境可注入 `sentence-transformers` 的 CrossEncoder
- scorer 失败时返回原始排序（fallback）

**面试要点**：
- "CrossEncoder 为什么精度高？" → query 和 doc 联合编码，交互注意力
- "为什么用依赖注入？" → 解耦 + 可测试性
- "Bi-Encoder vs Cross-Encoder？" → Bi-Encoder 分离编码可预计算快但精度低，Cross-Encoder 联合编码精度高但慢

### 15.7 B7 阶段工厂注册汇总

| 工厂 | 支持后端 |
|------|---------|
| `LLMFactory` | `fake`, `openai`, `azure`, `deepseek`, `ollama` |
| `EmbeddingFactory` | `fake`, `openai`, `azure`, `ollama` |
| `SplitterFactory` | `fake`, `recursive` |
| `VectorStoreFactory` | `fake`, `chroma` |
| `RerankerFactory` | `none`, `llm`, `cross_encoder` |
| `EvaluatorFactory` | `custom` |
| `VisionLLMFactory` | `fake`, `azure`, `none` |

---

## 16. Stage B8 完成总结：Vision LLM 抽象 + Azure Vision 实现

**完成时间**：2025-08-23
**测试总数**：421 全部通过（1.17s）

### 16.1 B8.1: BaseVisionLLM 抽象基类

| 文件 | 代码行 | 关键设计 |
|------|--------|---------|
| `base_vision_llm.py` | ~100 | ABC 抽象基类，定义 `caption_image()` + `model_name` + `provider_name` |

**核心设计决策**：
- **不继承 BaseLLM**：接口不同（`caption_image` vs `chat`），遵循接口隔离原则 (ISP)
- **入参是 Base64 而非文件路径**：解耦图片来源，可测试性好
- **降级策略**：失败时返回空字符串，不阻断摄取流程

**面试要点**：
- "Vision LLM 和普通 LLM 的区别？" → 多了图像理解能力，content 从 string 变成 list[dict]
- "为什么不继承 BaseLLM？" → 接口不同 + 职责不同 + 接口隔离原则
- "为什么传 Base64 而非 path？" → 解耦 + 可测试性
- "图片怎么参与 RAG 检索？" → 先 captioning 转文本，再 embed

### 16.2 B8.2: FakeVisionLLM 测试桩

| 文件 | 代码行 | 关键设计 |
|------|--------|---------|
| `vision_factory.py` (FakeVisionLLM) | ~40 | 返回固定/可预测的图片描述，不依赖真实 API |

### 16.3 B8.3: AzureVisionLLM 实现

| 文件 | 代码行 | 测试数 | 关键设计 |
|------|--------|--------|---------|
| `azure_vision_llm.py` | ~170 | 12 (MockTransport) | httpx 封装 Azure OpenAI Vision API，multimodal content 格式 |

**核心流程**：
1. 构造 data URI：`data:image/png;base64,{base64_str}`
2. 构造 multimodal content：`[{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": data_uri}}]`
3. POST 到 Azure OpenAI deployment 端点（与 AzureLLM 相同的 URL 格式）
4. 解析 `choices[0].message.content` 获取描述文本

**与 AzureLLM 的区别**：
- AzureLLM: `messages.content` 是 string
- AzureVisionLLM: `messages.content` 是 `list[dict]`（多模态格式）
- 面试考点："为什么 content 从 string 变成 list？" → 需要同时传文本和图片

### 16.4 B8.4: VisionLLMFactory 工厂

| 文件 | 代码行 | 测试数 | 关键设计 |
|------|--------|--------|---------|
| `vision_factory.py` | ~120 | 5 | 工厂模式 + NoneVisionLLM 空对象模式 |

**降级策略**：
- `enabled=false` → 返回 `NoneVisionLLM`（空对象，不报错）
- `NoneVisionLLM.caption_image()` → 返回空字符串 `""`
- 调用方不需要判空（空对象实现了完整接口）
- 面试考点："Vision 不启用时工厂返回什么？" → NoneVisionLLM（不是 None）

### 16.5 B8 测试覆盖

| 测试类别 | 数量 | 关键测试 |
|---------|------|---------|
| BaseVisionLLM ABC 契约 | 3 | 不可实例化、子类未实现→TypeError、完整实现→可用 |
| FakeVisionLLM | 6 | 继承关系、provider/model_name、默认/自定义 response |
| NoneVisionLLM | 3 | 空对象模式、返回空字符串、model/provider name |
| AzureVisionLLM 初始化 | 6 | 缺 api_key/endpoint/deployment → LLMError |
| AzureVisionLLM caption | 6 | 成功/空图片/默认prompt/401/429/400/解析失败 |
| VisionLLMFactory 工厂 | 5 | disabled→None、fake/azure 路由、未知→Error、register() |
| **合计** | **30** | |

### 16.6 B8 面试问答

| 问题 | 回答 |
|------|------|
| "Vision LLM 和普通 LLM 的区别？" | Vision LLM 接受图片输入，content 从 string 变成 list[dict] |
| "为什么不继承 BaseLLM？" | 接口不同（caption_image vs chat）+ 接口隔离原则 |
| "为什么传 Base64 而非文件路径？" | 解耦图片来源 + 可测试性 |
| "Azure Vision API 的请求格式？" | multimodal content: [{type: text}, {type: image_url}] |
| "Vision 不启用时工厂返回什么？" | NoneVisionLLM 空对象（不是 None） |
| "Vision 失败怎么办？" | 返回空字符串，由调用方决定是否跳过 |
| "图片怎么参与 RAG 检索？" | 先 captioning 转文本 → 再 embed → 参与向量检索 |

---

## 17. Stage C1 完成总结：Document/Chunk/ChunkRecord 数据契约

**完成时间**：2025-08-23
**测试总数**：452 全部通过（1.11s）

### 17.1 文件结构

| 文件 | 代码行 | 关键设计 |
|------|--------|---------|
| `src/core/types.py` | ~230 | 契约中心模式 — 全链路共享 Document/Chunk/ChunkRecord |
| `tests/unit/test_data_contracts.py` | ~300 | 31 个测试覆盖所有数据契约 |

### 17.2 三个核心数据契约

#### Document — 文档对象（摄取链路起点）

```python
@dataclass
class Document:
    doc_id: str          # 文档唯一标识（source_path 的 SHA256 前 16 位）
    source_path: str     # 源文件路径（溯源 + 增量摄取）
    text: str            # 文档全文（Markdown 格式，经 BaseLoader 转换）
    metadata: dict       # 文档级元数据（doc_type, title, file_hash 等）
```

生命周期：BaseLoader 读取文件 → 生成 Document → DocumentChunker 切分为 list[Chunk]

#### Chunk — 文档分块（带位置信息和溯源）

```python
@dataclass
class Chunk:
    chunk_id: str                      # 块唯一标识
    doc_id: str                        # 所属文档 ID
    text: str                          # 块文本内容
    index: int                         # 块在文档中的序号（0-based）
    source_ref: str = ""               # 溯源引用（如 "doc.pdf#page=3"）
    metadata: dict = {}                # 块级元数据（继承 Document + Splitter 添加）
    image_ids: list = []              # 块包含的图片 ID 列表
    has_unprocessed_images: bool = False  # 是否有未描述的图片（降级标记）
```

生命周期：DocumentChunker 切分 → Transform 链精化 → Encoder 编码 → ChunkRecord

#### ChunkRecord — 带向量的 Chunk（用于存储）

```python
@dataclass
class ChunkRecord:
    chunk_id: str          # 块唯一标识（与 Chunk.chunk_id 一致）
    doc_id: str            # 所属文档 ID
    text: str              # 块文本内容
    embedding: list[float]  # 向量（维度由 Embedding 模型决定）
    metadata: dict          # 元数据
    source_ref: str = ""   # 溯源引用
```

生命周期：Chunk + embedding → ChunkRecord → VectorUpserter → VectorStore

### 17.3 ID 生成策略（面试核心考点）

```python
chunk_id = f"{doc_id}_{index:04d}_{content_hash[:8]}"
# 示例：a3f2b1c9d8e7f6a5_0003_7b8a3c91

doc_id = hashlib.sha256(source_path.encode()).hexdigest()[:16]
content_hash = hashlib.sha256(content.encode()).hexdigest()[:8]
```

| 组成 | 长度 | 作用 |
|------|------|------|
| doc_id | 16 字符 | 文档唯一标识（SHA256 前 16 位） |
| index | 4 字符 | 块序号（0000-9999，零填充） |
| content_hash | 8 字符 | 内容指纹（SHA256 前 8 位） |

**幂等性保证**：
- 内容不变 → content_hash 不变 → id 不变 → upsert 覆盖（幂等）
- 内容变更 → content_hash 变化 → id 变化 → 新记录（增量更新）
- 面试考点："为什么 ID 包含 content_hash？" → 内容变更时自动生成新 ID

### 17.4 转换函数

| 函数 | 输入 | 输出 | 用途 |
|------|------|------|------|
| `generate_doc_id(source_path)` | str | str (16字符) | 根据文件路径生成文档 ID |
| `generate_chunk_id(doc_id, index, content)` | str+int+str | str (~30字符) | 生成 Chunk ID |
| `chunk_to_record(chunk, embedding)` | Chunk+list[float] | ChunkRecord | Chunk + 向量 → 存储记录 |
| `record_to_vector_record(record)` | ChunkRecord | VectorRecord | 存储记录 → 向量数据库输入 |

### 17.5 ChunkRecord vs VectorRecord（面试必问）

| 维度 | ChunkRecord | VectorRecord |
|------|-------------|--------------|
| 用途 | 摄取链路中间产物 | 向量数据库输入单元 |
| 来源 | Chunk + Embedding | ChunkRecord 转换 |
| 字段 | chunk_id, doc_id, text, embedding, metadata, source_ref | id, embedding, text, metadata |
| 区别 | 有 doc_id 和 source_ref 独立字段 | doc_id 和 source_ref 合并到 metadata |

面试考点："为什么需要两层数据结构？" → 分离业务逻辑（ChunkRecord）和存储逻辑（VectorRecord）

### 17.6 C1 测试覆盖

| 测试类别 | 数量 | 关键测试 |
|---------|------|---------|
| ID 生成函数 | 4 | 返回类型、确定性、不同路径不同 ID、ID 长度 |
| Document 契约 | 5 | 基本字段、默认 metadata、实例独立性、相等性、富 metadata |
| Chunk 契约 | 7 | 基本字段、默认值、独立性、图片字段、has_unprocessed_images |
| ChunkRecord 契约 | 5 | 基本字段、默认值、独立性、相等性 |
| 转换函数 | 4 | chunk_to_record、record_to_vector_record、深拷贝、字段完整性 |
| ID 策略集成 | 4 | 格式检查、零填充、幂等性、内容变更检测 |
| **合计** | **31** | |

### 17.7 C1 面试问答

| 问题 | 回答 |
|------|------|
| "什么是契约中心模式？" | 所有模块共享 types.py 中的数据定义，避免格式转换 |
| "Document/Chunk/ChunkRecord 的数据流？" | Document → 切分 → Chunk → 编码 → ChunkRecord → 存储 |
| "chunk_id 为什么要包含 content_hash？" | 内容变更时自动生成新 ID，实现增量更新和幂等性 |
| "Chunk 和 Document 的区别？" | Chunk 带位置信息（index）和溯源（source_ref） |
| "ChunkRecord 和 VectorRecord 的区别？" | ChunkRecord 是中间产物（有 doc_id 独立字段），VectorRecord 是数据库输入（doc_id 合并到 metadata） |
| "has_unprocessed_images 什么时候为 True？" | Vision LLM 不可用时，图片无法描述 |
| "为什么用 SHA256 生成 ID 而非文件名？" | 唯一性 + 固定长度 + 不含特殊字符 |

---

## 18. Stage C2 完成总结：SHA256 文件完整性检查

**完成时间**：2025-08-23
**测试总数**：476 全部通过（1.22s）

### 18.1 文件结构

| 文件 | 代码行 | 关键设计 |
|------|--------|---------|
| `src/libs/loader/file_integrity.py` | ~190 | SHA256 哈希追踪 + JSON 持久化 + 增量判断 |
| `src/libs/loader/__init__.py` | 10 | 模块导出 |
| `tests/unit/test_file_integrity.py` | ~250 | 24 个测试覆盖全部场景 |

### 18.2 核心接口

| 方法 | 签名 | 用途 |
|------|------|------|
| `compute_hash` | `(file_path: str) -> str` | 计算文件 SHA256（分块 8KB 读取） |
| `has_changed` | `(file_path: str) -> bool` | 判断文件是否变更/首次出现 |
| `update_hash` | `(file_path: str) -> str` | 更新文件哈希记录 |
| `get_hash` | `(file_path: str) -> str\|None` | 获取已存储的哈希 |
| `save` | `() -> None` | 持久化到 JSON 文件 |
| `load` | `() -> None` | 从 JSON 加载（容错：文件损坏→空字典） |
| `remove` | `(file_path: str) -> bool` | 删除记录（DocumentManager 用） |
| `clear` | `() -> None` | 清空所有记录（--force 全量重跑用） |

### 18.3 SHA256 原理

| 特性 | 说明 |
|------|------|
| 固定长度 | 任意输入 → 64 字符十六进制输出 |
| 雪崩效应 | 输入 1 bit 变化 → 输出完全不同 |
| 不可逆 | 无法从哈希反推原文 |
| 确定性 | 相同输入 → 永远相同输出 |

分块读取设计：8KB 块循环读取，避免大文件 OOM。

### 18.4 增量摄取流程

```
首次运行:
  文件A → has_changed? → True → 处理 → update_hash(A)
  文件B → has_changed? → True → 处理 → update_hash(B)

第二次运行（文件A未变, 文件B修改了）:
  文件A → has_changed? → False → 跳过（增量优化）
  文件B → has_changed? → True → 重新处理 → update_hash(B)
```

### 18.5 持久化设计

- **格式**：JSON 文件 `{source_path: file_hash}` 映射
- **路径**：`data/db/file_hashes.json`
- **load 容错**：文件不存在 → 空字典；JSON 损坏 → 空字典（不阻断流程）
- **save 策略**：自动创建父目录；不自动 save（由 Pipeline 批量调用减少 IO）

### 18.6 C2 测试覆盖

| 测试类别 | 数量 | 关键测试 |
|---------|------|---------|
| 基本属性 | 3 | db_path、count、get_all_paths |
| compute_hash | 4 | 返回类型、哈希长度64、确定性、文件不存在→Error |
| has_changed | 4 | 新文件True、未变更False、修改True、不同文件不同哈希 |
| update/get_hash | 3 | update返回哈希、get获取存储哈希、未记录→None |
| save/load | 4 | save创建文件、load恢复、load不存在、load损坏JSON容错 |
| remove/clear | 3 | 删除存在→True、删除不存在→False、clear清空 |
| 增量摄取场景 | 3 | 首次全量、第二次跳过、修改检测 |
| **合计** | **24** | |

### 18.7 C2 面试问答

| 问题 | 回答 |
|------|------|
| "为什么要做文件完整性检查？" | 增量摄取（跳过未变更文件）+ 幂等性保证 |
| "SHA256 的特点？" | 固定长度 + 雪崩效应 + 不可逆 + 确定性 |
| "增量摄取怎么实现的？" | 首次运行存哈希 → 后续运行对比哈希 → 不同则重新处理 |
| "为什么不一次性 read 整个文件？" | 大文件可能 OOM → 8KB 分块读取 |
| "为什么用 JSON 而非 SQLite？" | 简单 + 单文件 + 无依赖 + 量小 |
| "load 失败怎么办？" | 容错降级为空字典，不阻断流程 |
| "--force 全量重跑怎么实现？" | clear() 清空哈希记录 → 所有文件都判定为变更 |

---

## 19. Stage C3 完成总结：BaseLoader 抽象基类与 PDF Loader

**完成时间**：2025-08-24
**测试总数**：505 passed, 1 skipped（1.46s）

### 19.1 文件结构

| 文件 | 代码行 | 关键设计 |
|------|--------|---------|
| `src/libs/loader/base_loader.py` | ~70 | ABC 抽象基类，定义 `load(path) -> Document` |
| `src/libs/loader/pdf_loader.py` | ~130 | MarkItDown PDF→Markdown 转换，标题提取 |
| `src/libs/loader/loader_factory.py` | ~200 | 工厂模式 + FakeLoader + MarkdownLoader + TextLoader |
| `src/libs/loader/__init__.py` | 30 | 模块导出（含 C2 的 FileIntegrityChecker） |
| `tests/unit/test_loader_contract.py` | ~280 | 30 个测试（29 passed, 1 skipped） |

### 19.2 核心接口

| 方法 | 签名 | 用途 |
|------|------|------|
| `BaseLoader.load` | `(path: str) -> Document` | 加载文件，返回统一 Document 对象 |
| `LoaderFactory.create` | `(file_type: str) -> BaseLoader` | 按类型名创建 Loader |
| `LoaderFactory.create_for_file` | `(path: str) -> BaseLoader` | 按文件扩展名自动路由 |

### 19.3 Loader 实现矩阵

| Loader | 支持扩展名 | 转换方式 | 特点 |
|--------|-----------|---------|------|
| `PdfLoader` | `.pdf` | MarkItDown → Markdown | 延迟导入 markitdown，标题提取 |
| `MarkdownLoader` | `.md`, `.markdown` | 直接读取 | 文本即 Markdown，无需转换 |
| `TextLoader` | `.txt` | 直接读取 | 纯文本加载 |
| `FakeLoader` | `.fake` | 不读文件 | 测试桩，返回预设 Document |

### 19.4 关键设计决策

**为什么先转 Markdown 再切分？**
- Markdown 有天然的结构标记（标题、段落、代码块、列表）
- RecursiveCharacterTextSplitter 可以按 Markdown 结构智能切分
- 比直接从 PDF 提取纯文本再切分质量高得多

**为什么延迟导入 markitdown？**
- markitdown 是可选依赖，不安装时其他 Loader 仍可用
- 减少启动时间
- 未安装时抛出 LoaderError 并提示安装

**metadata 标准字段**：
```python
{
    "source_path": "/path/to/doc.pdf",  # 源文件路径
    "doc_type": "pdf",                  # 文档类型
    "title": "文档标题",                  # 从 Markdown # 提取或用文件名
    "file_name": "doc.pdf",             # 文件名
    "images": [],                       # 图片列表（当前空，C7 阶段完善）
}
```

### 19.5 C3 测试覆盖

| 测试类别 | 数量 | 关键测试 |
|---------|------|---------|
| BaseLoader ABC 契约 | 3 | 不可实例化、子类未实现→TypeError、完整实现→可用 |
| FakeLoader | 4 | 返回 Document、metadata 必需字段、自定义文本 |
| MarkdownLoader | 5 | 加载 MD、文件不存在、空文件、标题回退到文件名 |
| TextLoader | 3 | 加载 TXT、文件不存在、空文件 |
| PdfLoader | 5 | ABC 继承、扩展名、文件不存在、不支持的格式、sample PDF |
| LoaderFactory | 8 | create 各类型、未知→Error、create_for_file 路由、register() |
| **合计** | **30** | (29 passed, 1 skipped: sample.pdf 不存在) |

### 19.6 C3 面试问答

| 问题 | 回答 |
|------|------|
| "Loader 的职责边界？" | 格式转换 + 结构抽取，不负责切分（切分由 DocumentChunker 负责） |
| "为什么要抽象 BaseLoader？" | 统一接口 + 可插拔 + 新增格式不改 Pipeline 代码 |
| "为什么要先转 Markdown？" | 结构标记 + Splitter 对 Markdown 友好 + 比纯文本切分质量高 |
| "为什么选 MarkItDown？" | 直接产出 Markdown + 多格式支持 + Microsoft 开源 |
| "markitdown 未安装怎么办？" | 延迟导入 → LoaderError 提示安装 → 其他 Loader 不受影响 |
| "metadata 包含什么？" | source_path, doc_type, title, file_name, images |
| "图片提取失败怎么办？" | 降级跳过，不阻塞文本解析（C7 阶段完善） |
| "新增格式需要改什么？" | 实现 BaseLoader + 在 _LOADERS 和 _EXT_MAP 注册 |

---

## 20. C4 完成：Splitter 集成（DocumentChunker 适配器层）

### 20.1 文件结构

| 文件 | 代码行 | 关键设计 |
|------|--------|---------|
| `src/ingestion/chunking/document_chunker.py` | ~240 | 适配器模式，Document→List[Chunk] 转换 + 图片分发 |
| `src/ingestion/chunking/__init__.py` | 12 | 模块导出（DocumentChunker, ChunkingError） |
| `tests/unit/test_document_chunker.py` | ~550 | 37 个测试（全部通过） |

### 20.2 核心接口

| 方法 | 签名 | 用途 |
|------|------|------|
| `DocumentChunker.__init__` | `(settings: Settings)` | 通过 SplitterFactory 获取 splitter 实例 |
| `split_document` | `(document: Document) -> List[Chunk]` | 完整的 Document→Chunks 转换流程 |
| `_generate_chunk_id` | `(doc_id, index, text) -> str` | 生成确定性 Chunk ID（委托 generate_chunk_id） |
| `_inherit_metadata` | `(document, chunk_index, chunk_text) -> dict` | 元数据继承 + 图片引用按需分发 |
| `splitter_name` | `-> str` (property) | 返回当前 Splitter 名称 |

### 20.3 DocumentChunker 的 6 个增值功能

| # | 增值功能 | 实现方式 |
|---|---------|---------|
| 1 | Chunk ID 生成 | 调用 `generate_chunk_id(doc_id, index, text)` → `{doc_id}_{index:04d}_{hash8}` |
| 2 | 元数据继承 | 深拷贝 Document.metadata（排除 images）到每个 Chunk.metadata |
| 3 | 添加 chunk_index | 在 metadata 中记录序号（0-based），用于排序和定位 |
| 4 | 建立 source_ref | `"{source_path}#chunk={index}"`，支持溯源 |
| 5 | 图片引用按需分发 | 扫描 `[IMAGE: {id}]` 占位符 → 分发到对应 chunk 的 images/image_refs |
| 6 | 类型转换 | `List[str]` → `List[Chunk]` 对象，符合 core.types 契约 |

### 20.4 图片分发逻辑

**核心问题**：为什么不能简单继承或丢弃文档级 images？

```
Document.metadata["images"] = [img_001, img_002, img_003]  # 文档级（全部）
                    ↓ Splitter 切分
Chunk 0: "...[IMAGE: img_001]..."  → metadata["images"] = [img_001]  # 子集
Chunk 1: "plain text..."           → metadata 中无 images 字段      # 不含
Chunk 2: "...[IMAGE: img_002]..."  → metadata["images"] = [img_002]  # 子集
```

**分发规则**：
- `image_refs`：与 chunk 文本中的 `[IMAGE: id]` 占位符一致（去重后）
- `images`：仅包含在 Document.metadata["images"] 中找到的 ImageRef 子集
- 无占位符的 chunk：不含 `images` 和 `image_refs` 字段
- 重复占位符：`image_refs` 去重，`images` 去重
- 未知 image_id：`image_refs` 包含该 id，`images` 不包含对应 ImageRef

**正则匹配**：`r'\[IMAGE:\s*(\S+?)\s*\]'` 匹配 `[IMAGE: {id}]` 格式

### 20.5 职责边界（面试考点）

| 层 | 输入 → 输出 | 职责 |
|---|-----------|------|
| `libs.splitter` | `str → List[str]` | 纯文本切分，不涉及业务对象 |
| `DocumentChunker` | `Document → List[Chunk]` | 业务适配器：ID + 元数据 + 溯源 + 图片分发 |

**数据流对比**
```commandline
DocumentChunker 做的事              RecursiveSplitter 做的事
                                    
Document 对象                       
  ├── text: "RAG 是检索增强..."      "RAG 是检索增强..."
  ├── doc_id: "doc1"           ──→     │
  └── metadata: {...}                split_text()
                                       │
                                    递归切分：
                                    1. 按 \n\n 分
                                    2. 超长的继续按 \n 分
                                    3. 合并到接近 chunk_size
                                    4. 添加 overlap
                                       │
                                       ▼
                                    ["RAG 是检索增强...", "生成模型可以..."]
                                       │
                               ←── 返回 list[str]
                                       │
DocumentChunker 继续处理：              │
  ├── 生成 chunk_id                   │
  ├── 继承 metadata                   │
  ├── 设置 chunk_index                │
  ├── 建立 source_ref                 │
  ├── 扫描图片占位符                   │
  └── 包装成 Chunk 对象               │
       │                              │
       ▼                              │
  list[Chunk]                         │
  ├── Chunk(chunk_id="doc1_0000_a3f2", doc_id="doc1", text="RAG是...",
  │         index=0, source_ref="doc.pdf#chunk=0", metadata={...})
  └── Chunk(chunk_id="doc1_0001_b8c1", doc_id="doc1", text="生成模型...",
            index=1, source_ref="doc.pdf#chunk=1", metadata={...})
```

**为什么分离？** → 单一职责原则（SRP）：Splitter 可复用，DocumentChunker 可替换

### 20.6 C4 测试覆盖

| 测试类别 | 数量 | 关键测试 |
|---------|------|---------|
| 基本切分 | 3 | 返回 Chunk 列表、文本一致、chunk_size 影响数量 |
| ID 确定性 | 4 | 重复切分 ID 一致、ID 唯一、ID 格式、内容变更 ID 变化 |
| 元数据继承 | 3 | 字段继承、chunk_index、深拷贝 |
| source_ref | 2 | 指向父文档、包含 chunk 序号 |
| 图片分发 | 8 | 有占位符→有 images、无占位符→无 images、refs 一致、子集、去重、未知 id |
| 异常处理 | 6 | 空文档、Splitter 异常、空结果、全空白、空白过滤、不支持 provider |
| 配置驱动 | 2 | chunk_size 影响、chunk_overlap 影响 |
| 类型契约 | 4 | 字段完整、文本非空、index 递增、doc_id 一致 |
| 属性 | 2 | splitter_name（fake/recursive） |
| 集成 | 3 | RecursiveSplitter 完整流程、确定性、图片端到端 |
| **合计** | **37** | (37 passed, 0 failed) |

### 20.7 C4 面试问答

| 问题 | 回答 |
|------|------|
| "DocumentChunker 做了什么 Splitter 没做的？" | ID 生成 + 元数据继承 + chunk_index + source_ref + 图片分发 + 类型转换 |
| "为什么用适配器模式？" | libs.splitter 只处理 str→List[str]，不依赖业务对象；DocumentChunker 适配为 Document→List[Chunk] |
| "Chunk ID 为什么要包含 content_hash？" | 内容变更 → hash 变化 → 新 ID → 增量更新 |
| "图片分发为什么不能整体继承？" | 下游 C7 ImageCaptioner 需要按 chunk 定位图片，整体继承会导致每个 chunk 都处理全部图片 |
| "无占位符的 chunk 有 images 字段吗？" | 没有，只有含 [IMAGE: id] 占位符的 chunk 才有 images/image_refs |
| "image_refs 和 images 的区别？" | image_refs = 占位符中的 id 列表（去重）；images = 在文档 images 中找到的 ImageRef 子集 |
| "空白片段怎么处理？" | split_document 跳过纯空白片段，只保留有效 chunk |
| "Splitter 异常怎么处理？" | SplitterError → 包装为 ChunkingError，上层统一捕获 |

---

## 21. C5 完成：Transform 抽象基类 + ChunkRefiner（规则去噪 + LLM 增强 + 降级）

### 21.1 文件结构

| 文件 | 代码行 | 关键设计 |
|------|--------|---------|
| `src/core/trace/trace_context.py` | ~120 | TraceContext 最小实现（trace_id + record_stage + finish） |
| `src/core/trace/__init__.py` | 8 | 模块导出 |
| `src/ingestion/transform/base_transform.py` | ~80 | BaseTransform ABC + TransformError |
| `src/ingestion/transform/chunk_refiner.py` | ~310 | 规则去噪 + LLM 增强 + 失败降级 |
| `src/ingestion/transform/__init__.py` | 16 | 模块导出 |
| `config/prompts/chunk_refinement.txt` | 16 | LLM 增强 prompt 模板（{text} 占位符） |
| `tests/fixtures/noisy_chunks.json` | ~120 | 8 个典型噪声场景（fixtures 驱动测试） |
| `tests/unit/test_chunk_refiner.py` | ~370 | 28 个单元测试（Mock LLM，全部通过） |
| `tests/integration/test_chunk_refiner_llm.py` | ~170 | 4 个集成测试（无 API key 自动 skip） |

### 21.2 核心接口

| 方法/类 | 签名 | 用途 |
|---------|------|------|
| `BaseTransform.transform` | `(chunks, trace?) -> List[Chunk]` | 抽象方法，子类必须实现 |
| `ChunkRefiner.__init__` | `(settings, llm?, prompt_path?)` | 依赖注入 LLM + 加载 prompt |
| `ChunkRefiner.transform` | `(chunks, trace?) -> List[Chunk]` | 主入口：规则去噪 → LLM 增强 → 降级 |
| `ChunkRefiner._rule_based_refine` | `(text: str) -> str` | 确定性规则去噪（正则 + 代码块保护） |
| `ChunkRefiner._llm_refine` | `(text, trace?) -> (str\|None, str\|None)` | LLM 增强，失败返回 (None, reason) |
| `ChunkRefiner._load_prompt` | `(prompt_path?) -> str` | 从文件加载 prompt，支持内置 fallback |
| `TraceContext.record_stage` | `(stage, data?, duration_ms?)` | 记录阶段数据 |
| `TraceContext.finish` | `-> dict` | 汇总所有阶段，返回可序列化 dict |

### 21.3 两阶段清洗策略

```
chunk.text
  │
  ├─ 1. 规则去噪（确定性，零成本，始终执行）
  │    ├─ 去除不可见字符（零宽空格/控制字符/Unicode 非字符）
  │    ├─ 去除 HTML 注释 <!-- -->
  │    ├─ 去除页码行（第X页/Page X/- X -/X/Y）
  │    ├─ 去除分隔线（---/===/***，3+ 符号）
  │    ├─ 行内空白合并 + 行首尾 strip
  │    └─ 3+ 连续换行 → 2 个换行
  │
  ├─ 2. LLM 增强（可选，非确定性，失败降级）
  │    ├─ 用规则去噪后的文本填充 {text} 占位符
  │    ├─ 调用 LLM.chat(messages)
  │    └─ 成功：返回 LLM 重写文本，refined_by="llm"
  │       失败：返回 None + fallback 原因
  │
  └─ 降级路径（LLM 失败时）
       ├─ 使用规则去噪结果
       ├─ metadata["refined_by"] = "rule"
       └─ metadata["refinement_fallback"] = 原因
```

**顺序很重要（面试考点）**：先规则后 LLM → LLM 拿到已去噪的干净文本，prompt 更短更准 + 成本更低

### 21.4 代码块保护机制

```python
# 原始文本
"示例代码：\n```python\ndef   process(  data ):\n    if   data:\n        return    data [ 0 ]\n```\n说明文字。"

# 规则去噪后（代码块内部格式不变，外部去噪）
"示例代码：\n```python\ndef   process(  data ):\n    if   data:\n        return    data [ 0 ]\n```\n说明文字。"
```

- 按 ``` 分离文本段，奇数部分是代码内容（原样保留），偶数部分应用去噪规则
- 代码块内的缩进/空白/符号有语法意义（Python 缩进），不能被空白规则破坏

### 21.5 降级机制设计

| 触发场景 | fallback 原因 | metadata 标记 |
|---------|--------------|---------------|
| LLM API 异常 | `llm_error: <详情>` | `refined_by="rule"` + `refinement_fallback` |
| 意外异常（非 LLMError） | `llm_unexpected_error: <详情>` | `refined_by="rule"` + `refinement_fallback` |
| LLM 返回空 | `llm_empty_response` | `refined_by="rule"` + `refinement_fallback` |
| LLM 工厂创建失败 | use_llm 降级为 False | `refined_by="rule"`（无 fallback 标记） |
| 单 chunk 处理异常 | `exception: <详情>` | `refined_by="error"` + `refinement_fallback` |

**Fail-Safe vs Fail-Fast**：Transform 链中 Fail-Safe（降级继续），配置加载 Fail-Fast（立即崩溃）

### 21.6 8 个噪声场景（fixtures）

| 场景 | 描述 | 关键验证 |
|------|------|---------|
| typical_noise_scenario | 多余空白 + 分隔线 + HTML 注释 + 页码 | 综合噪声去除 |
| ocr_errors | 零宽字符 + Unicode 非字符 | 不可见字符去除 |
| page_header_footer | 4 种页码格式 | 页码行去除 |
| excessive_whitespace | 行内连续空格 + 多换行 | 空白合并 |
| format_markers | HTML 注释 + 分隔线（表格分隔行保留） | 不误伤表格 |
| clean_text | 干净 Markdown 文本 | 不过度清理 |
| code_blocks | 代码块含特殊缩进 | 代码格式保留 |
| mixed_noise | 零宽字符 + 页码 + 空白 + 注释 + 代码块 | 混合场景 |

### 21.7 C5 测试覆盖

| 测试类别 | 数量 | 关键测试 |
|---------|------|---------|
| BaseTransform ABC 契约 | 3 | 不可实例化、子类未实现→TypeError、完整实现→可用 |
| TraceContext | 3 | trace_id 唯一、record_stage 存储、finish 汇总 |
| 规则去噪 fixtures | 8 | 8 个噪声场景参数化测试 |
| 保留能力 | 2 | Markdown 结构保留、[IMAGE: id] 占位符保留 |
| LLM 模式 | 3 | 成功返回、收到规则去噪后文本、空响应降级 |
| 降级行为 | 3 | LLMError 降级、意外异常降级、工厂失败降级 |
| 配置开关 | 3 | use_llm=False 不调用、True 调用、settings.yaml 加载 |
| Prompt 加载 | 2 | 文件加载 + fallback 默认 |
| 异常隔离 | 1 | 单 chunk 异常不影响其他 |
| **单元合计** | **28** | (28 passed) |
| LLM 集成 | 4 | 真实调用 + 质量 + 降级 + trace（无 key skip） |

### 21.8 C5 面试问答

| 问题 | 回答 |
|------|------|
| "ChunkRefiner 做了什么？" | 规则去噪（确定性）+ 可选 LLM 增强（语义级清洗）+ 失败降级（不阻塞 ingestion） |
| "为什么规则在前 LLM 在后？" | 降成本（LLM 拿到干净文本 prompt 更短）+ 确定性兜底（LLM 失败有规则结果） |
| "LLM 失败怎么办？" | 降级到规则结果，metadata 标记 refined_by="rule" + fallback 原因，不阻塞 Pipeline |
| "代码块为什么不能去空白？" | Python 缩进有语法意义，去空白会破坏代码 |
| "Fail-Safe 和 Fail-Fast 的区别？" | Fail-Safe：数据处理降级继续；Fail-Fast：配置错误立即崩溃 |
| "什么是 Mock vs Stub？" | Stub 返回固定值（FakeLLM）；Mock 记录调用 + 可配置行为 + 可验证调用次数 |
| "TraceContext 有什么用？" | 记录各阶段数据（阶段名/耗时/元数据），用于调试和性能分析 |
| "单个 chunk 异常怎么处理？" | 保留原文 + metadata 标记 refined_by="error"，不影响其他 chunk |
| "prompt 文件不存在怎么办？" | 用内置默认 prompt 模板，组件仍可用（Fail-Safe） |

---

## 22. C6：MetadataEnricher（规则增强 + 可选 LLM 增强 + 降级）

### 22.1 设计目标

为每个 chunk 生成语义元数据（`title`/`summary`/`tags`），用于检索结果展示、过滤和聚类。

| 模式 | title 来源 | summary 来源 | tags 来源 | 成本 |
|------|-----------|-------------|----------|------|
| 规则模式（兜底） | Markdown 标题/首行截断20字 | 前100字截断到句子边界 | CJK 2-6字 + EN 3+字母词频 TopN | 零成本 |
| LLM 模式（核心） | LLM 语义理解生成 | LLM 50-100字摘要 | LLM 提取 3-5 关键词 | API 调用 |

### 22.2 降级机制

| 触发场景 | fallback 原因 | metadata 标记 |
|---------|--------------|-------------|
| LLM API 异常 | `llm_error` | `enriched_by="rule"` + `enrichment_fallback` |
| LLM 返回空 | `llm_empty_response` | `enriched_by="rule"` + `enrichment_fallback` |
| JSON 解析失败 | `llm_json_parse_error` | `enriched_by="rule"` + `enrichment_fallback` |
| 单 chunk 处理异常 | `exception: <详情>` | `enriched_by="error"` + `enrichment_fallback` |

LLM 响应容错：三级解析（直接 json.loads → 正则提取 JSON 块 → 提取代码块 JSON），都失败降级到规则结果。

### 22.3 C6 测试覆盖

| 测试类别 | 数量 | 关键测试 |
|---------|------|---------|
| BaseTransform 继承 | 2 | 子类验证、transform 签名 |
| 规则模式 | 5 | 标题提取、句子边界截断、词频提取、三字段非空 |
| 规则边界 | 3 | 空文本、短文本、max_tags 限制 |
| LLM 模式 | 3 | 成功返回、tags 截断、缺少字段用规则补 |
| LLM 响应解析 | 3 | 纯 JSON、带文字 JSON、无效 JSON |
| 降级行为 | 3 | LLMError、空响应、非 JSON |
| 配置开关 | 2 | use_llm=False/True |
| 异常隔离 + prompt | 2 | 单 chunk 异常隔离、prompt 文件/fallback |
| Trace + Settings | 2 | settings.yaml 加载、trace 阶段记录 |
| **单元合计** | **26** | 26 passed |

---

## 23. C7：ImageCaptioner（Vision LLM 生成 caption + 降级不阻塞）

### 23.1 设计目标

当 Vision LLM 可用且 chunk 包含图片引用时，为图片生成文字描述（caption），写入 chunk metadata。
图片不能直接 embed，先 captioning 转文本，再参与检索（多模态 RAG 核心链路）。

### 23.2 降级矩阵

| 条件 | 行为 | chunk 标记 |
|------|------|-----------|
| Vision LLM 禁用 | 跳过 | `has_unprocessed_images=True` |
| 无 image_ids | 正常跳过 | `has_unprocessed_images=False` |
| 图片数据缺失 | 跳过该图 | `has_unprocessed_images=True` |
| LLM 调用失败 | 跳过该图 | `has_unprocessed_images=True` |
| 成功 | 写入 caption | `has_unprocessed_images=False` |

### 23.3 图片数据解析

| 来源 | 字段 | 优先级 |
|------|------|--------|
| base64 内联 | `img["data"]` | 1（最高） |
| 文件路径 | `img["path"]` | 2（读取后 base64 编码） |
| 都没有 | — | 返回空 → 降级 |

关键设计：部分成功也有效 — 多图场景中部分成功写入 caption，部分失败标记未处理。

### 23.4 C7 测试覆盖

| 测试类别 | 数量 | 关键测试 |
|---------|------|---------|
| BaseTransform 继承 + 基础 | 2 | 子类验证、空列表 |
| 启用模式 | 4 | 生成 caption、上下文注入、多图、文件路径 |
| 降级模式 | 4 | 禁用、LLMError、空响应、数据缺失 |
| 无图片跳过 | 2 | 无图原样返回、空 image_ids |
| 图片数据解析 | 3 | data 优先、路径不存在、metadata image_refs |
| 异常隔离 | 2 | 单 chunk 异常隔离、非 list 抛异常 |
| 配置 + prompt | 2 | settings.yaml 加载、prompt 文件/fallback |
| Trace | 1 | trace 阶段记录 |
| **单元合计** | **21** | 21 passed |

---

## 24. C8：DenseEncoder（稠密向量编码）

### 24.1 设计目标

将 Chunk 列表批量送入 BaseEmbedding，生成向量，组合成 ChunkRecord。

摄取链路位置：Loader → Splitter → Transform 链 → **DenseEncoder** → VectorUpserter

### 24.2 与 Transform 的区别

| 维度 | Transform（C5-C7） | DenseEncoder（C8） |
|------|-------------------|-------------------|
| 职责 | 增强（去噪/元数据/图片描述） | 编码（文本→向量） |
| 可选性 | 可选/可降级 | 必需 |
| 失败策略 | 降级不阻塞（Fail-Safe） | 抛异常（Fail-Fast） |
| 输出类型 | `list[Chunk]` | `list[ChunkRecord]` |

### 24.3 校验机制

| 校验 | 规则 | 失败行为 |
|------|------|---------|
| 数量一致 | `len(vectors) == len(chunks)` | 抛 `EmbeddingError` |
| 维度一致 | `len(vec) == embedding.dimensions` | 抛 `EmbeddingError` |
| 空输入 | `len(chunks) == 0` → 返回空列表 | 不调用 API |

### 24.4 C8 测试覆盖

| 测试类别 | 数量 | 关键测试 |
|---------|------|---------|
| 基础 + 空输入 | 3 | 空列表返回空、空列表+trace、单 chunk |
| 编码正确性 | 4 | 数量一致、维度一致、字段映射、批量调用一次 |
| 批量处理 | 2 | 20 个大批量、文本按顺序提取 |
| 属性 | 2 | dimensions、model_name |
| 错误场景 | 2 | 数量不一致、维度不匹配 |
| Trace + Settings | 2 | trace 阶段记录、工厂自动创建 |
| **单元合计** | **15** | 15 passed |

---

## 25. C9：SparseEncoder（BM25 统计与输出契约）

### 25.1 设计目标

对 chunks 进行分词和词频统计，输出 `SparseVector` 结构，供后续 `bm25_indexer` 构建倒排索引。

### 25.2 SparseVector 数据结构

```python
@dataclass
class SparseVector:
    chunk_id: str           # 对应的 chunk ID
    doc_id: str             # 所属文档 ID
    terms: dict[str, float] # {term: tf} 词频映射
    doc_len: int            # 文档长度（token 数，BM25 长度归一化用）
```

### 25.3 分词策略（无外部分词器依赖）

| 语言 | 策略 | 示例 |
|------|------|------|
| 英文 | 3+ 字母词提取，小写化，去停用词 | "Database Query" → ["database", "query"] |
| 中文 | Bigram（2-gram） | "向量数据库" → ["向量", "量数", "数据", "据库"] |
| 混合 | 英文词 + 中文 bigram 合并 | "RAG 系统" → ["rag", "系统"] |

### 25.4 BM25 公式与语料库统计

```
Score(D, Q) = Σ IDF(qi) · (f(qi,D)·(k1+1)) / (f(qi,D)+k1·(1-b+b·|D|/avgdl))
IDF(qi) = ln((N - n(qi) + 0.5) / (n(qi) + 0.5) + 1)
k1=1.2（词频饱和）, b=0.75（长度归一化）
```

`compute_corpus_stats()` 输出：N（文档总数）、avgdl（平均文档长度）、df（文档频率）、idf（预计算 IDF）。
`compute_bm25_score()` 静态方法供 sparse_retriever 使用。

### 25.5 与 DenseEncoder 对比

| 维度 | DenseEncoder (C8) | SparseEncoder (C9) |
|------|-------------------|-------------------|
| 输出 | `list[ChunkRecord]`（含 dense embedding） | `list[SparseVector]`（含 term 频率） |
| 依赖 | Embedding API（外部） | 纯本地计算（无 API） |
| 失败策略 | 抛异常（API 不可用） | 不会失败（本地计算） |
| 用途 | 向量数据库 | BM25 倒排索引 |
| 互补性 | 语义相似性（同义词） | 精确匹配（专有名词） |

### 25.6 C9 测试覆盖

| 测试类别 | 数量 | 关键测试 |
|---------|------|---------|
| 基础 + 空输入 | 3 | 空列表返回空、单 chunk、数量一致 |
| 分词正确性 | 4 | 英文分词、短词过滤、中文 bigram、混合文本 |
| 词频统计 | 3 | 词频正确、doc_len=tokens 数、dict 结构 |
| 空文本处理 | 2 | 空文本、纯空白文本 |
| 语料库统计 | 3 | N/avgdl/df/idf、DF 统计、IDF 稀有性 |
| BM25 分数 | 2 | 匹配正分、不匹配零分 |
| Trace | 1 | 阶段数据记录 |
| **单元合计** | **18** | 18 passed |
| 全量测试 | 650 | 650 passed, 5 skipped |

### 25.7 C6-C9 面试问答

| 问题 | 回答 |
|------|------|
| "MetadataEnricher 做了什么？" | 为 chunk 生成 title/summary/tags：规则模式基于文本统计提取（兜底），LLM 模式语义理解生成（核心），失败降级 |
| "LLM 输出不可靠怎么办？" | 三级容错解析：直接 json.loads → 正则提取 JSON 块 → 提取代码块 JSON，都失败降级到规则结果 |
| "ImageCaptioner 降级策略？" | Vision LLM 不可用/数据缺失/调用失败 → 跳过，标记 has_unprocessed_images=True，不阻塞 pipeline |
| "DenseEncoder 和 Transform 的区别？" | Transform 是可选增强（降级安全），Encoder 是必需编码（失败抛异常） |
| "为什么批量 embed？" | 减少 API 调用次数 → 降成本 + 降延迟 + 减少网络开销 |
| "Sparse 和 Dense 有什么区别？" | Dense 捕获语义相似性（向量），Sparse 捕获精确匹配（关键词），两者互补 |
| "中文怎么分词？" | Bigram 2-gram，无 jieba 依赖，虽然不精确但足够 BM25 统计 |
| "BM25 的 k1 和 b 是什么？" | k1 控制词频饱和（默认1.2），b 控制长度归一化（默认0.75） |
| "空文本怎么处理？" | SparseEncoder 输出 terms={}, doc_len=0，不抛异常 |
| "IDF 为什么这样算？" | 词越稀有 IDF 越大越重要，IDF=ln((N-n+0.5)/(n+0.5)+1) |

---

## 26. C10：BatchProcessor（批处理编排）

### 26.1 设计目标

将 chunks 分 batch，逐批驱动 DenseEncoder + SparseEncoder 编码，合并结果。

摄取链路位置：... → Transform 链 → **BatchProcessor** → Storage

### 26.2 分批策略

| 场景 | batch_size | chunks 数 | 批次数 | 批次大小 |
|------|-----------|----------|--------|---------|
| 验收标准 | 2 | 5 | 3 | [2, 2, 1] |
| 整除 | 3 | 6 | 2 | [3, 3] |
| 大 batch | 100 | 5 | 1 | [5] |

**顺序稳定性**：按顺序切分，保持 chunk 顺序，跨批次连续合并。

### 26.3 架构设计

```
chunks → _split_batches() → [[c0,c1], [c2,c3], [c4]]
                                    ↓
         逐批: DenseEncoder.encode(batch) → ChunkRecord[]
               SparseEncoder.encode(batch) → SparseVector[]
                                    ↓
         合并: all_dense.extend(...) + all_sparse.extend(...)
                                    ↓
         trace 记录每批: {index, chunks, dense, sparse, duration_ms}
```

### 26.4 编码器组合

| 模式 | Dense | Sparse | 输出 |
|------|-------|--------|------|
| 双编码 | ✅ | ✅ | (list[ChunkRecord], list[SparseVector]) |
| 仅 Sparse | ❌ | ✅ | ([], list[SparseVector]) |

Dense 编码器可选（注入 None 时跳过 Dense 编码），Sparse 编码器始终执行。

### 26.5 C10 测试覆盖

| 测试类别 | 数量 | 关键测试 |
|---------|------|---------|
| 分批逻辑 | 3 | 5/bs=2→3批、整除无余、大batch单批 |
| 基础 + 空输入 | 2 | 空列表返回空、空列表+trace |
| 双编码驱动 | 3 | Dense+Sparse双编码、数量一致、多批收集 |
| 仅 Sparse | 2 | 无Dense只Sparse、大批量 |
| 顺序稳定性 | 2 | chunk_id按序、跨批连续 |
| Trace + 属性 | 2 | trace批次详情、batch_size属性 |
| **单元合计** | **14** | 14 passed |
| 全量测试 | 664 | 664 passed, 5 skipped |

### 26.6 C10 面试问答

| 问题 | 回答 |
|------|------|
| "BatchProcessor 做了什么？" | 将 chunks 分 batch，逐批驱动 Dense+Sparse 编码，合并结果保持顺序 |
| "为什么要分 batch？" | Embedding API 有批量大小限制 + 内存控制 + 错误隔离 |
| "batch_size 怎么选？" | 看 API 限制（OpenAI 单次 2048）+ 网络条件 + 内存，推荐 100-500 |
| "顺序怎么保证？" | 按顺序切分 + 按顺序合并（extend），跨批次连续 |
| "Dense 编码器可选吗？" | 是的，注入 None 时跳过 Dense，只做 Sparse 编码 |
| "每批耗时怎么记录？" | trace 的 batches 数组记录每批的 index/chunks/dense/sparse/duration_ms |

---

## 27. C11：BM25Indexer（倒排索引构建与持久化）

### 27.1 设计目标

接收 SparseEncoder 的 `list[SparseVector]`，计算 IDF，构建倒排索引，持久化到 `data/db/bm25/`。

摄取链路位置：... → SparseEncoder → **BM25Indexer** → data/db/bm25/
检索链路位置：query → tokenizer → **BM25Indexer.search()** → top_k chunk_ids

### 27.2 倒排索引结构

```json
{
  "N": 3,
  "avgdl": 2.67,
  "k1": 1.2,
  "b": 0.75,
  "index": {
    "database": {
      "idf": 0.470,
      "postings": [
        {"chunk_id": "c0", "tf": 1.0, "doc_length": 3},
        {"chunk_id": "c1", "tf": 1.0, "doc_length": 3}
      ]
    }
  }
}
```

### 27.3 IDF 计算

公式：`IDF(term) = ln((N - df + 0.5) / (df + 0.5) + 1)`

| Term | DF | N | IDF | 含义 |
|------|----|---|-----|------|
| database | 2 | 3 | 0.470 | 出现在 2/3 文档中，较常见 |
| index | 1 | 3 | 0.981 | 只在 1 个文档中，较稀有 |

**+1 的作用**：防止 IDF 为负值（当 df > N/2 时经典 IDF 会产生负值）。

### 27.4 核心方法

| 方法 | 功能 | 场景 |
|------|------|------|
| `build(vectors)` | 全量构建索引 | 首次构建 |
| `load()` | 从文件加载索引 | 服务启动 |
| `search(query_terms, top_k)` | BM25 查询返回 top_k | 检索 |
| `rebuild(vectors)` | 清空重建 | 手动重建 |
| `upsert(vectors)` | 增量更新（新增/更新文档） | 增量摄取 |

**build vs upsert**：build 清空旧索引全量重建，upsert 合并新旧文档后重建。
**upsert 实现**：从现有索引提取已有 SparseVector，合并新文档，重新 build（正确性优先，性能可优化）。

### 27.5 查询效率

倒排索引查询复杂度：O(Σ |postings(term)|) — 只遍历包含 query term 的文档，非全量扫描。

### 27.6 C11 测试覆盖

| 测试类别 | 数量 | 关键测试 |
|---------|------|---------|
| 构建基础 | 3 | 基本构建、空列表、文件持久化 |
| IDF 准确性 | 2 | IDF 值一致、稀有 term IDF 更高 |
| 查询 | 3 | 返回匹配文档、top_k 限制、分数降序 |
| 持久化 round-trip | 3 | build→load→查询一致、文件不存在抛异常、统计数据一致 |
| 重建 | 1 | rebuild 替换旧索引 |
| 增量更新 | 2 | upsert 新增文档、upsert 更新已有文档 |
| 边界 + 属性 | 2 | 空索引查询、无匹配返回空 |
| **单元合计** | **16** | 16 passed |
| 全量测试 | 680 | 680 passed, 5 skipped |

### 27.7 C11 面试问答

| 问题 | 回答 |
|------|------|
| "BM25Indexer 做了什么？" | 接收 SparseVector，计算 IDF，构建倒排索引，持久化到文件系统 |
| "为什么叫倒排索引？" | 反转了映射方向：term→doc（而非 doc→term），查询时直接定位包含 query term 的文档 |
| "IDF 公式 +1 的作用？" | 防止 IDF 为负值（当 df > N/2 时经典 IDF 会产生负值） |
| "build 和 upsert 的区别？" | build 清空重建，upsert 合并新旧文档后重建 |
| "为什么用 JSON 持久化？" | 可读性好 + 调试方便 + 跨语言兼容（生产可用 binary 提升性能） |
| "倒排索引查询为什么快？" | 只遍历包含 query term 的文档（O(Σ|postings|)），非全量扫描 |
| "增量更新怎么实现？" | 从现有索引提取已有 SparseVector，合并新文档后重新 build |

---

## 28. C12：VectorUpserter（向量存储与幂等性保证）

### 28.1 设计目标

接收 DenseEncoder 的 `list[ChunkRecord]`，转换为 VectorRecord，调用 BaseVectorStore 幂等写入。

摄取链路位置：... → DenseEncoder → **VectorUpserter** → 向量数据库
为 D2 (DenseRetriever) 提供可查询的向量数据库。

### 28.2 幂等性设计

| 场景 | chunk_id | 行为 |
|------|---------|------|
| 同一内容重复 upsert | 不变 | 覆盖旧记录，不产生重复 |
| 内容变更 | 变化 | 新 chunk_id → 新记录（旧记录需手动删除） |
| 批量 upsert | 各自独立 | 每条记录独立 upsert |

chunk_id = `hash(source_path + chunk_index + content_hash[:8])` — 确定性生成，相同输入相同 id。

### 28.3 ChunkRecord → VectorRecord 转换

| ChunkRecord 字段 | VectorRecord 字段 | 说明 |
|-----------------|-----------------|------|
| `chunk_id` | `id` | 字段重命名 |
| `embedding` | `embedding` | 直接复制 |
| `text` | `text` | 直接复制 |
| `metadata` + `doc_id` + `source_ref` | `metadata` | doc_id 和 source_ref 合并到 metadata |

使用 `record_to_vector_record()` 工具函数完成转换。

### 28.4 核心方法

| 方法 | 功能 | 场景 |
|------|------|------|
| `upsert(records)` | 批量写入向量数据库 | 摄取链路 |
| `delete(chunk_ids)` | 按 chunk_id 删除 | 文档更新 |
| `delete_by_doc_id(doc_id)` | 按 doc_id 删除文档所有向量 | 文档下架 |

### 28.5 C12 测试覆盖

| 测试类别 | 数量 | 关键测试 |
|---------|------|---------|
| 基础 + 空输入 | 2 | 空列表返回0、单条写入 |
| 幂等性 | 3 | 同一记录两次相同id、内容变更不同id、覆盖旧记录 |
| 批量写入 | 2 | 批量保持顺序、数量一致 |
| Record 转换 | 3 | id映射、doc_id合并metadata、source_ref合并metadata |
| 删除 | 2 | 按 chunk_id 删除、按 doc_id 删除 |
| Trace + 属性 | 2 | trace阶段记录、vector_store属性 |
| **单元合计** | **14** | 14 passed |
| 全量测试 | 694 | 694 passed, 5 skipped |

### 28.6 C12 面试问答

| 问题 | 回答 |
|------|------|
| "VectorUpserter 做了什么？" | 接收 ChunkRecord，转换为 VectorRecord，调用 BaseVectorStore 幂等写入 |
| "upsert 和 insert 的区别？" | upsert 幂等，相同 id 覆盖不重复；insert 可能产生重复 |
| "幂等性怎么保证？" | chunk_id 确定性生成（hash），相同内容→相同 id→覆盖旧记录 |
| "为什么 doc_id 要合并到 metadata？" | 向量数据库只存 id/embedding/text/metadata，doc_id 作为 metadata 用于过滤和溯源 |
| "内容变更后旧向量怎么办？" | 旧 chunk_id 不变但内容已变→新 chunk_id→旧记录需手动删除或 GC |
| "delete_by_doc_id 怎么实现？" | 调用 VectorStore.delete_by_metadata({"doc_id": doc_id}) |

---

## 29. C13：ImageStorage（图片文件存储与索引映射）

### 29.1 设计目标

保存图片到 `data/images/{collection}/`，使用 SQLite 记录 image_id→path 映射。

摄取链路位置：Loader 提取图片 → **ImageStorage** 保存文件 + 索引

### 29.2 为什么用 SQLite 而非 JSON

| 维度 | file_integrity (JSON) | image_storage (SQLite) |
|------|----------------------|----------------------|
| 数据量 | 小（文件数有限） | 大（每页多张图） |
| 查询方式 | 全量遍历 | 索引查询（collection / doc_hash） |
| 并发需求 | 单线程 | WAL 模式并发安全 |
| 写入频率 | 低（每次摄取一次） | 高（批量保存图片） |

### 29.3 数据库表结构

```sql
CREATE TABLE image_index (
    image_id TEXT PRIMARY KEY,
    file_path TEXT NOT NULL,
    collection TEXT,
    doc_hash TEXT,
    page_num INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_collection ON image_index(collection);
CREATE INDEX idx_doc_hash ON image_index(doc_hash);
```

### 29.4 文件存储 + 索引分离

| 存储 | 内容 | 位置 |
|------|------|------|
| 文件系统 | 图片二进制 | `data/images/{collection}/{image_id}.{ext}` |
| SQLite | image_id→file_path 映射 + 元数据 | `data/db/image_index.db` |

**为什么不存 BLOB？** 文件系统更适合大文件 + 可直接 serve + 不膨胀数据库。

### 29.5 WAL 模式（Write-Ahead Logging）

- 写入先写到 WAL 文件，异步合并到主数据库
- 读写不互斥（并发安全）
- 面试考点："为什么要 WAL？" → 并发安全 + 写入性能

### 29.6 核心方法

| 方法 | 功能 |
|------|------|
| `save(image_id, image_data, collection, doc_hash, page_num)` | 保存图片 + 写索引（幂等：INSERT OR REPLACE） |
| `get_path(image_id)` | 查找文件路径 |
| `get_by_collection(collection)` | 按 collection 批量查询 |
| `get_by_doc_hash(doc_hash)` | 按文档哈希查询所有图片 |
| `delete(image_id)` | 删除单张（文件 + 索引） |
| `delete_by_doc_hash(doc_hash)` | 删除文档所有图片 |

### 29.7 C13 测试覆盖

| 测试类别 | 数量 | 关键测试 |
|---------|------|---------|
| 保存 + 文件存在 | 4 | 文件创建、路径正确、幂等覆盖、扩展名 |
| 查询路径 | 2 | 存在返回路径、不存在返回 None |
| 按 collection 查询 | 2 | 批量查询、空 collection |
| 按 doc_hash 查询 | 2 | 查询文档图片、不存在空列表 |
| 删除 | 3 | 单个删除、不存在返回False、按doc_hash删除 |
| 持久化 + 统计 | 3 | 跨实例持久化、总数统计、按collection统计 |
| **单元合计** | **16** | 16 passed |
| 全量测试 | 710 | 710 passed, 5 skipped |

### 29.8 C13 面试问答

| 问题 | 回答 |
|------|------|
| "ImageStorage 做了什么？" | 保存图片二进制到文件系统 + SQLite 记录 image_id→path 映射 |
| "为什么用 SQLite 而非 JSON？" | 图片数量大 + 需要索引查询 + WAL 并发安全 |
| "为什么不把图片存 SQLite BLOB？" | 文件系统更适合大文件 + 可直接 serve + 不膨胀数据库 |
| "WAL 模式有什么好处？" | 读写不互斥（并发安全）+ 写入性能好 |
| "幂等性怎么保证？" | INSERT OR REPLACE + 文件覆盖写入 |
| "删除策略是什么？" | 先查索引获取路径→删文件→删索引，文件删除失败不阻塞索引删除 |

---

## 30. C14：Pipeline 编排（MVP 串起来）

### 30.1 设计目标

串行执行摄取链路：integrity → load → split → transform → encode → store，对失败步骤抛出明确异常。

### 30.2 Pipeline 流程

```
file_path
  ↓
1. Integrity: FileIntegrityChecker.has_changed() → 未变更则跳过
  ↓
2. Load: LoaderFactory.create_for_file().load() → Document
  ↓
3. Split: DocumentChunker.split_document() → list[Chunk]
  ↓
4. Transform: ChunkRefiner → MetadataEnricher → ImageCaptioner → list[Chunk]
  ↓
5. Encode: BatchProcessor.process() → (list[ChunkRecord], list[SparseVector])
  ↓
6. Store: VectorUpserter.upsert() + BM25Indexer.upsert() → 持久化
  ↓
7. Update hash: FileIntegrityChecker.update_hash() → 增量摄取标记
```

### 30.3 异常策略

| 阶段 | 失败策略 | 原因 |
|------|---------|------|
| Integrity | Fail-Fast（文件不存在→异常） | 无法处理不存在的文件 |
| Load | Fail-Fast（解析失败→异常） | 无文本无法后续 |
| Split | Fail-Fast（切分失败→异常） | 无 chunk 无法后续 |
| Transform | Fail-Safe（降级继续） | 增强可选，不应阻塞 |
| Encode | Fail-Fast（编码失败→异常） | 无向量无法存储 |
| Store | Fail-Fast（存储失败→异常） | 数据丢失不可恢复 |

### 30.4 Transform 链执行顺序

1. **ChunkRefiner** → 去噪（干净文本有利于后续）
2. **MetadataEnricher** → 补元数据（title/summary/tags）
3. **ImageCaptioner** → 图片描述（最可能降级，放最后）

### 30.5 核心接口

| 方法 | 功能 |
|------|------|
| `ingest(file_path, force=False)` | 摄取单个文件 |
| `ingest_batch(file_paths, force=False)` | 批量摄取（异常隔离） |
| `on_progress(callback)` | 注册进度回调 |

### 30.6 增量摄取

- 首次摄取：`has_changed() → True` → 全量处理 → `update_hash()` → `save()`
- 二次摄取：`has_changed() → False` → 跳过（status="skipped"）
- force=True：跳过完整性检查，强制重新摄取

### 30.7 C14 测试覆盖

| 测试类别 | 数量 | 关键测试 |
|---------|------|---------|
| 基础摄取流程 | 3 | Markdown摄取成功、结果结构、trace记录 |
| 增量摄取 | 2 | 未变更跳过、force强制重摄 |
| 进度回调 | 2 | 回调被调用、回调数据正确 |
| 批量摄取 | 2 | 多文件批量、失败隔离 |
| 错误处理 | 2 | 不存在文件抛异常、失败结果有错误信息 |
| **集成合计** | **11** | 11 passed |
| 全量测试 | 721 | 721 passed, 5 skipped |

### 30.8 C14 面试问答

| 问题 | 回答 |
|------|------|
| "Pipeline 做了什么？" | 串行执行 integrity→load→split→transform→encode→store，串联摄取链路 |
| "Transform 链为什么这个顺序？" | 去噪优先（干净文本）→ 元数据次之 → 图片最后（最可能降级） |
| "增量摄取怎么实现？" | FileIntegrityChecker 对比 SHA256，未变更跳过，force=True 强制重摄 |
| "批量摄取失败怎么处理？" | 异常隔离：单文件失败标记 status=failed，不影响其他文件 |
| "进度回调怎么实现？" | on_progress 注册回调函数，每个阶段切换时触发（回调模式） |
| "哪些阶段可以降级？" | 只有 Transform 链可以降级（Fail-Safe），其他阶段失败必须抛异常 |

---

## 31. C15：脚本入口 ingest.py（离线可用）

### 31.1 设计目标

实现 `scripts/ingest.py` CLI 入口，支持 `--collection`、`--path`、`--force`，调用 IngestionPipeline 完成摄取。

### 31.2 CLI 参数

| 参数 | 缩写 | 说明 |
|------|------|------|
| `--path` | `-p` | 文件或目录路径（必填） |
| `--force` | `-f` | 强制重新摄取（跳过增量检查） |
| `--collection` | `-c` | 文档集合名称 |
| `--config` | | 配置文件路径（默认 config/settings.yaml） |
| `--verbose` | `-v` | 详细日志输出 |

### 31.3 使用方式

```bash
# 摄取单个文件
python scripts/ingest.py --path document.pdf

# 摄取目录
python scripts/ingest.py --path ./documents/

# 强制重新摄取
python scripts/ingest.py --path document.pdf --force

# 指定 collection
python scripts/ingest.py --path document.pdf --collection my_project
```

### 31.4 目录递归扫描

```python
SUPPORTED_EXTENSIONS = {".pdf", ".md", ".markdown", ".txt", ".docx"}

def collect_files(path: str) -> list[str]:
    # 文件 → [path]
    # 目录 → 递归扫描所有支持的扩展名
```

### 31.5 退出码策略

| 场景 | 退出码 |
|------|--------|
| 成功 | 0 |
| 跳过（未变更） | 0 |
| 全部失败（无成功无跳过） | 1 |
| 路径不存在 | 1 |

### 31.6 C15 测试覆盖

| 测试类别 | 数量 | 关键测试 |
|---------|------|---------|
| 基础 CLI 运行 | 2 | 单文件摄取成功、输出汇总 |
| 增量摄取 | 2 | 未变更跳过、变更后重摄 |
| force 强制重摄 | 1 | --force 强制重新摄取 |
| 目录摄取 | 1 | 目录下多文件摄取 |
| 错误处理 | 1 | 不存在路径→非零退出码 |
| **E2E 合计** | **7** | 7 passed (subprocess 真实 CLI) |
| 全量测试 | 728 | 728 passed, 5 skipped |

### 31.7 C15 面试问答

| 问题 | 回答 |
|------|------|
| "为什么需要 CLI 入口？" | 离线批量摄取，不需要启动 MCP Server |
| "argparse vs click？" | argparse 标准库无依赖，click 更优雅但需额外安装 |
| "增量摄取怎么实现？" | FileIntegrityChecker 对比 SHA256，未变更→status=skipped |
| "跳过的文件算失败吗？" | 不算，退出码 0（只有全部失败才返回 1） |
| "目录摄取怎么实现？" | 递归扫描支持扩展名（.pdf/.md/.txt/.docx），sorted 排序 |




