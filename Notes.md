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
