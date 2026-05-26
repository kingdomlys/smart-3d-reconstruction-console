# 智能 3D 视觉重建控制台 - 需求与开发流程文档

## 1. 产品概述 (Product Overview)
本系统是一个本地部署的智能 3D 视觉重建控制台。系统通过统一的 Web UI 接收用户上传的单张或多张图像，通过后端的智能控制面分配至最优的 3D 重建算法管线（单图生成式 TripoSR、多图几何式/神经渲染式 COLMAP+3DGS），并提供跨格式 (`.glb`, `.ply`/splat) 的统一 Web 3D 预览能力。

## 2. 系统架构设计 (System Architecture)
系统采用前后端分离与进程级模块化解耦的设计理念，核心组件如下：

*   **Frontend (前端 WebUI):** 基于 React + Three.js (R3F)。负责图像上传、任务状态实时监控 (WebSocket)、异构 3D 资产渲染无缝切换 (GLTF 模型与 3DGS 渲染)。
*   **Agent Control Plane (智能控制面):** 基于 FastAPI。负责接收 HTTP 请求、生成任务 UUID、校验图像数量、统一下发任务到全局队列，并维护 WebSocket 通信和轻量级 SQLite 数据库任务记录。
*   **Task Queue & GPU Runner:** 单例任务消费引擎，确保同一时间只有一个需要显存的 Worker 在运行，避免 OOM。
*   **Model Workers (模型执行节点):** 独立封装的算法脚本。由于技术栈冲突，**不同 Worker 运行在完全独立的 Conda 虚拟环境中**。控制面通过 `subprocess` 作为子进程唤起 Worker，运行结束时进程销毁，实现操作系统级别的完全显存回收。

## 3. 核心规范设计

### 3.1 统一存储与数据目录结构
所有任务文件在局域网内基于 UUID 组织，结构如下：
```text
/workspace/data/tasks/
  └── {task_uuid}/
       ├── inputs/      # 用户上传的原始图片
       ├── interim/     # 中间产物 (如 rembg 的去背图、colmap 的稀疏点云/位姿文件)
       ├── outputs/     # 最终产出的模型文件 (.glb 或 .ply)
       └── logs.txt     # 任务执行日志与 stdout 捕获
```

### 3.2 智能路由逻辑
*   `if image_count == 1`: 分发至 **Worker-TripoSR** 环境。
*   `if image_count > 1`: 
    *   执行 **Worker-COLMAP** 获取相机位姿。
    *   级联执行 **Worker-3DGS** 训练并输出密集点云/splats。

### 3.3 任务状态机
定义标准化任务状态，便于前端展示精细进度：
`Pending` -> `Running (Sub-states: Extracting_Features, Training_##%)` -> `Completed` / `Failed`

---

## 4. 开发阶段规划 (Development Phases)

本项目坚持“小步快跑，单链路优先”的原则。

### Phase 1: 基础设施构建 (Infrastructure & API)
*   **目标:** 搭建基础通信骨架。
*   **任务:**
    1. 初始化 FastAPI 后端项目结构。
    2. 实现 `POST /api/tasks` 接收图片，建立 UUID 目录体系。
    3. 集成 SQLite 持久化任务元数据。
    4. 实现简单的单例任务队列与 WebSocket 通道骨架（模拟耗时任务并推送进度）。

### Phase 2: TripoSR 单图流水线闭环 (MVP Pipeline)
*   **目标:** 跑通从上传图片到后端真正产出 3D 模型的物理闭环。
*   **任务:**
    1. 在新的 Conda 环境中配置 TripoSR 与 `rembg` 依赖。
    2. 编写 `worker_tripo.py` 包装器。
    3. FastAPI 控制面通过 `subprocess` 调用 `worker_tripo.py`，阻塞等待并提取产物。
    4. 完善 WebSocket 推送：开始推理 -> 推理完成 -> 输出 `.glb` 路径。

### Phase 3: Web 3D 渲染器集成 (Universal Viewer)
*   **目标:** 为产物提供本地化可视验证机制。
*   **任务:**
    1. 搭建 React+Vite 前端应用框架。
    2. 使用 `react-three-fiber` 组件读取 Phase 2 产出的 `.glb` 模型并渲染。
    3. 集成 WebSocket 监听，实现上传->进度条展示->模型自动加载的全流程交互。

### Phase 4: 多图流水线 (COLMAP + 3DGS) 与环境隔离
*   **目标:** 支持复杂的多图 3D 重建流程。
*   **任务:**
    1. 环境搭建：系统级配置 COLMAP，Conda 环境配置 3DGS 训练工具链。
    2. 编写 `worker_colmap.py` 提取位姿。
    3. 编写 `worker_3dgs.py` 进行神经渲染训练，同时需要截获 stdout 实时解析 `Iteration xx/xxxx` 进度并记录到共享文件或输出给控制面。
    4. 完善核心控制面的智能路由代码。

### Phase 5: 系统健壮性优化 (Robustness Polish)
*   **目标:** 将 Demo 升级为可用的系统服务。
*   **任务:**
    1. 异常处理捕获：处理 OOM、位姿提取失败等极端情况，保证控制面不崩溃并准确重置 GPU runner。
    2. 文件清理机制：定时或手动清理 `/data/tasks` 下过期的临时文件。
    3. 前端 UI 细节打磨：加载骨架屏、下载原始 3D 资产按钮等。

## 5. 日常开发规范
- **代码提交:** 每个 Phase 结束后进行整体 Review 与提交。
- **环境要求:** Python 后端必须编写 `.env.example` 和 `requirements.txt` / `environment.yml`，严禁交叉污染全局依赖。
- **接口要求:** 提供一套规范的 OpenAPI (Swagger) 自动文档。
