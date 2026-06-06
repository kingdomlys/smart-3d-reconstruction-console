# 智能 3D 重建控制台 - 开发计划草案

> 状态：已合并用户确认意见，待继续补充确认。
> 基线提交：`0b308ec Add TripoSR wrapper and third-party submodules`
> 远端分支：`origin/main`

## 1. 项目预期目标

构建一个本地部署的 3D 重建控制台。用户通过 Web UI 上传单张或多张图片，后端控制面自动选择合适的重建管线，实时推送任务状态，并在前端预览或下载生成的 3D 资产。

已确认的路线：

- 单图：优先完成 TripoSR 真实管线，输出 `.glb`。
- 多图：后续完成 COLMAP + 3D Gaussian Splatting，目标同时支持 `.ply` 与 splat 输出。
- 首个可用版本按 CUDA 环境设计，不把 CPU fallback 作为首要目标。
- 第三方依赖继续采用 Git submodule 记录固定版本。
- 当前阶段任务历史继续使用 SQLite，不引入 Redis/Celery 等额外队列系统。
- 上传限制：单次最多 8 张图片；单张图片分辨率最高 1080p，按 `1920x1080` 或等价最大像素数 `2073600` 控制。
- 任务产物目录应支持用户指定，不做自动清理。

## 2. 当前已完成模块

### 2.1 后端控制面

已完成：

- FastAPI 服务骨架。
- 健康检查接口。
- 图片上传与任务创建接口。
- 基于 UUID 的任务目录。
- SQLite 任务表。
- 任务查询与任务列表接口。
- 输出文件下载接口。
- WebSocket 任务状态推送。
- 进程内异步队列，当前串行执行任务。
- 每个任务写入 `logs.txt`。

主要文件：

- `backend/app/main.py`
- `backend/app/db.py`
- `backend/app/storage.py`
- `backend/app/tasks.py`

### 2.2 Worker 与算法接入

当前状态：

- 已有 TripoSR、COLMAP、3DGS 三类 worker 文件。
- 已有 TripoSR CLI 包装器：`backend/workers/triposr_infer.py`。
- 已有外部命令 hook：
  - `TRIPOSR_CMD`
  - `COLMAP_CMD`
  - `DGS_CMD`
- 当前 worker 仍处于“占位实现 + 外部命令包装”阶段。

需要调整的方向：

- 不再把核心算法实现放在项目目录外部。
- TripoSR、COLMAP、3DGS 三条方法都应在当前项目内形成明确实现入口。
- 第三方仓库只作为源码/模型依赖来源，不作为业务逻辑入口散落在项目外。
- 后续新增深度学习推理方法时，应通过统一接口注册，而不是继续复制临时 worker 脚本。

### 2.3 前端

已完成：

- React + Vite 应用骨架。
- 上传表单。
- 最近任务列表。
- 任务选择。
- WebSocket 状态订阅。
- 完成后自动拉取输出。
- GLB 预览能力。

主要文件：

- `frontend/src/App.jsx`
- `frontend/src/components/TaskViewer.jsx`
- `frontend/src/styles.css`

### 2.4 文档与依赖

已完成：

- 项目规划文档。
- Pipeline 安装文档。
- 开发日志。
- 环境变量样例。
- TripoSR、COLMAP、3DGS 安装脚本。
- 第三方仓库作为 submodule 记录：
  - `third_party/TripoSR`
  - `third_party/gaussian-splatting`

主要文件：

- `docs/PROJECT_PLAN.md`
- `docs/PIPELINE_SETUP.md`
- `docs/DEV_LOG.md`
- `backend/.env.example`
- `frontend/.env.example`
- `scripts/setup_triposr.ps1`
- `scripts/setup_colmap.ps1`
- `scripts/setup_3dgs.ps1`

## 3. 需要重构的核心方向：Pipeline/Worker 架构

当前 worker 方案的问题：

- 真实算法入口主要依赖环境变量指向外部脚本。
- 三种方法之间缺少统一接口。
- 任务输入、输出、日志、进度事件缺少稳定契约。
- 以后添加新的深度学习方法时，容易继续形成零散脚本。

目标架构：

```text
backend/
  app/
    main.py
    tasks.py
    storage.py
    db.py
    settings.py
  pipelines/
    base.py
    registry.py
    context.py
    triposr/
      pipeline.py
    colmap/
      pipeline.py
    gaussian_splatting/
      pipeline.py
  workers/
    run_pipeline.py
```

建议接口：

```python
class Pipeline:
    id: str
    name: str
    output_types: list[str]

    def supports(self, image_count: int, mode: str) -> bool:
        ...

    def run(self, context: PipelineContext) -> PipelineResult:
        ...
```

`PipelineContext` 应包含：

- `task_id`
- `mode`
- `inputs_dir`
- `interim_dir`
- `outputs_dir`
- `logs_path`
- `settings`
- `emit_event(payload)`

`PipelineResult` 应包含：

- `status`
- `primary_output_path`
- `outputs`
- `output_types`
- `metadata`
- `error`

注册策略：

- `triposr`：单图输入，输出 `.glb`。
- `colmap`：多图输入，输出相机位姿与稀疏点云中间产物。
- `gaussian_splatting`：消费 COLMAP 中间产物，输出 `.ply` 与 splat 资产。
- 未来新增方法：只需新增 `backend/pipelines/{method}/pipeline.py` 并注册到 `registry.py`。

保留 subprocess 的原因：

- 深度学习管线通常有独立环境和 CUDA 依赖。
- 子进程结束后更容易释放 GPU 显存。
- 但子进程入口应是项目内统一入口：`backend/workers/run_pipeline.py`。

## 4. 当前缺口与风险

### 4.1 配置与产物目录

问题：

- 后端当前未自动加载 `backend/.env`。
- `TASKS_ROOT` 在 `.env.example` 中存在，但代码仍使用固定路径。
- 用户希望任务产物目录可指定，不做自动清理。

计划：

- 新增 `backend/app/settings.py`。
- 支持从 `.env` 与环境变量读取 `TASKS_ROOT`。
- 后端启动时校验任务目录可写。
- 前端显示当前任务目录。
- 后续可增加设置接口，用于选择或修改任务产物目录。

### 4.2 上传限制与安全

问题：

- 当前直接使用上传文件名保存。
- 只有扩展名校验。
- 没有图片数量与分辨率限制。

计划：

- 单次最多允许 8 张图片。
- 单张图片最高 1080p：
  - 宽高不超过 `1920x1080`，或
  - 总像素数不超过 `2073600`。
- 使用安全文件名，禁止路径穿越。
- 使用 Pillow 读取图片头部并校验真实图片尺寸。
- 超限图片直接拒绝，暂不自动压缩或降采样。

### 4.3 任务生命周期

判断：

- 当前阶段保持 SQLite 是合适的。
- 项目是本地控制台，任务吞吐不高，暂不需要 Redis/Celery。
- 后续如果需要多机、多 GPU 或并发调度，再升级队列系统。

计划：

- 继续使用 SQLite 记录任务历史。
- 启动时将遗留的 `Running` 状态修正为 `Failed` 或 `Interrupted`。
- 增加任务日志接口。
- 增加任务重试接口。
- 视实际 subprocess 控制情况增加取消接口。

### 4.4 TripoSR 真实管线

问题：

- 当前默认未配置真实管线时会生成占位 GLB。
- 真实 TripoSR 执行还需要 CUDA 环境验证。

计划：

- 第一条真实管线优先完成 TripoSR。
- 把 TripoSR 实现收敛到 `backend/pipelines/triposr/pipeline.py`。
- 继续使用 `third_party/TripoSR` 作为源码依赖。
- 明确 CUDA 版本、模型权重、依赖安装方式。
- 真实输出 `.glb` 后在前端自动预览。

### 4.5 COLMAP + 3DGS 真实管线

问题：

- 多图链路目前仍是占位级。
- COLMAP 与 3DGS 的中间数据契约还未固定。
- `.ply` 与 splat 两种输出都需要支持。

计划：

- 先实现项目内 COLMAP pipeline，固定输出目录结构。
- 再实现项目内 Gaussian Splatting pipeline。
- 多图任务最终输出：
  - `.ply`：用于点云/高斯点云预览与下载。
  - splat 资产：用于后续专用 viewer 或下载。
- 训练进度需要从 stdout 或日志中解析为 WebSocket 事件。

### 4.6 前端预览器

问题：

- 当前只支持 GLB。
- `.ply` 和 splat 暂未预览。

计划：

- 保留 GLB viewer。
- 增加 PLY viewer。
- 增加 splat viewer；若第一版 viewer 尚不稳定，至少提供明确下载入口。
- 后端任务响应增加 `outputs` 与 `output_types`，前端按类型选择 viewer。

### 4.7 测试

问题：

- 当前缺少自动化测试。

计划：

- 增加后端 API 测试。
- 增加 pipeline contract 测试。
- 增加 worker dry-run 测试。
- 增加前端 build 检查。
- 对真实 CUDA 管线保留手工 smoke test 清单。

## 5. 开发里程碑

### Milestone 0 - 基线稳定与配置落地

目标：

让当前仓库从 GitHub 拉取后可复现、可配置、可继续开发。

任务：

- 确认 `origin/main` 基线提交为 `0b308ec`。
- 文档补充 submodule 初始化命令：
  - `git submodule update --init --recursive`
- 新增 `backend/app/settings.py`。
- 后端加载 `.env`。
- `TASKS_ROOT` 改为可配置任务产物目录。
- 启动时校验任务产物目录。
- 上传文件名安全处理。
- 上传数量限制为 8。
- 上传分辨率限制为 1080p。

验收标准：

- 本地 clone 后可初始化 submodule。
- 后端能读取配置。
- 任务产物可写入指定目录。
- 不再存在不安全文件名写入。

### Milestone 1 - Pipeline/Worker 架构重构

目标：

把现有临时 worker 收敛为项目内统一 pipeline 架构，为后续新增推理方法保留接口。

任务：

- 新建 `backend/pipelines/`。
- 定义 `Pipeline`、`PipelineContext`、`PipelineResult`。
- 新建 `registry.py`。
- 新建统一 worker 入口 `backend/workers/run_pipeline.py`。
- 将当前 TripoSR、COLMAP、3DGS 占位逻辑迁移为 pipeline。
- `backend/app/tasks.py` 改为通过 registry 路由 pipeline。

验收标准：

- 单图任务通过 `triposr` pipeline 执行。
- 多图任务通过 `colmap` + `gaussian_splatting` pipeline 执行。
- 以后新增方法只需新增 pipeline 并注册。

### Milestone 2 - TripoSR 单图真实闭环

目标：

完成上传单张图片到生成真实 `.glb` 并预览的闭环。

任务：

- 配置 TripoSR CUDA 环境。
- 验证 `third_party/TripoSR` 可运行。
- 将 `triposr_infer.py` 逻辑整合进 `backend/pipelines/triposr/pipeline.py`。
- 输出真实 `.glb`。
- 改善错误信息。
- 前端自动加载 `.glb`。

验收标准：

- 单张合法图片生成真实 `.glb`。
- 前端可预览。
- 任务日志能定位依赖、CUDA、模型权重和输出缺失问题。

### Milestone 3 - 任务体验与可靠性

目标：

让系统适合反复本地使用和调试。

任务：

- 增加任务日志 API。
- 增加输出文件列表 API。
- 增加任务重试。
- 增加下载按钮。
- 前端展示错误、日志和多输出资产。
- 后端启动时处理遗留 Running 状态。

验收标准：

- 失败任务可查看原因。
- 完成任务可下载所有输出。
- 用户可重新执行失败任务。

### Milestone 4 - COLMAP 多图真实管线

目标：

完成多图几何预处理。

任务：

- 在项目内实现 COLMAP pipeline。
- 固定输入输出契约。
- 验证小样本多图数据。
- 输出相机、图像、点云中间产物。
- 推送 COLMAP 进度事件。

验收标准：

- 多图任务能生成可供 3DGS 使用的 COLMAP 中间结果。
- 匹配失败、图片不足、相机估计失败等情况有明确错误。

### Milestone 5 - 3DGS 训练与双输出

目标：

完成多图任务的 `.ply` 与 splat 输出。

任务：

- 在项目内实现 Gaussian Splatting pipeline。
- 适配 `third_party/gaussian-splatting`。
- 从 COLMAP 中间结果启动训练。
- 解析训练进度。
- 标准化输出：
  - `.ply`
  - splat 资产
- 后端记录多个输出文件。

验收标准：

- 多图任务产生非占位 `.ply`。
- 多图任务产生可下载的 splat 资产。
- WebSocket 能显示训练进度。

### Milestone 6 - 统一预览器

目标：

前端支持所有核心输出类型。

任务：

- 保留 GLB 预览。
- 增加 PLY 预览。
- 增加 splat 预览。
- 根据 `output_types` 自动选择 viewer。
- 对暂不支持的输出保留下载入口。

验收标准：

- `.glb`、`.ply`、splat 至少都能被前端识别。
- `.glb` 和 `.ply` 可预览。
- splat 可预览或明确下载。

### Milestone 7 - 发布前整理

目标：

形成稳定的本地工具版本。

任务：

- 一键启动文档。
- 依赖故障排查文档。
- 后端测试。
- pipeline contract 测试。
- 前端 build 检查。
- GPU smoke test 清单。
- 检查 `.gitignore` 和生成物。

验收标准：

- 新环境可按文档完成 clone、submodule 初始化、依赖安装、启动、上传、推理、预览。
- 核心失败场景有明确处理方式。

## 6. 当前立即执行顺序

建议按以下顺序推进：

1. 完成 Milestone 0：配置、任务目录、上传安全与 1080p 限制。
2. 完成 Milestone 1：Pipeline/Worker 架构重构。
3. 完成 Milestone 2：TripoSR CUDA 真实闭环。
4. 完成 Milestone 3：日志、重试、多输出 API 与前端错误展示。
5. 再推进 COLMAP、3DGS 与统一 viewer。

