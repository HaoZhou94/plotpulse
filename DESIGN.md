# PlotPulse 剧情分标方案与迭代计划

## 1. 本项目真正需要拆分的对象

项目重点拆分视频剧情分析的算法流水线，而不是为了分层而拆分基础设施。当前算法链由八个可独立替换、独立测试的模块组成：

```text
视频
 ├─ 镜头检测
 ├─ 音频检测
 ├─ OCR检测
 └─ 视觉分析
       ↓
   时间轴融合
       ↓
   文本/事件语义分析
       ↓
   剧情分段
       ↓
   章节生成
       ↓
   确定性质量校验
```

镜头检测到章节生成均只保留私有模型接入契约，不提供默认模型，不生成模拟业务结果。测试中使用的假数据只验证模块接口和流水线编排，不参与生产运行。

## 2. 项目结构

```text
D:\plotpulse
├─ main.py                         # 命令行和服务启动入口
├─ models.py                       # 算法模块共享 DTO
├─ errors.py                       # 统一错误类型
├─ config.py                       # 环境配置
├─ logging_utils.py                # JSON 结构化日志
├─ media.py                        # 地址校验和 ffprobe
├─ quality.py                      # 章节结构质量校验
├─ pipeline.py                     # 只负责编排八个算法模块
├─ jobs.py                         # 异步任务、SQLite、回调
├─ api.py                          # Java 平台 HTTP API
├─ algorithms/
│  ├─ base.py                      # 算法模块最小公共接口
│  ├─ registry.py                  # 八个算法模块的组装点
│  ├─ shot_detection.py            # 镜头检测
│  ├─ audio_detection.py           # ASR/VAD/说话人/音频事件
│  ├─ ocr_detection.py             # OCR检测
│  ├─ visual_analysis.py           # 人物、场景、动作理解
│  ├─ timeline_fusion.py           # 多模态时间轴融合
│  ├─ semantic_analysis.py         # 文本与事件语义分析
│  ├─ plot_segmentation.py         # 剧情边界和段落
│  └─ chapter_generation.py        # 标题、摘要、标签和缩略图时间
├─ requirements.txt
├─ config.yaml                     # YAML运行配置
├─ .gitignore
└─ DESIGN.md
```

项目根目录不再嵌套同名包目录，也不创建或管理虚拟环境。运行环境由使用方自己的 conda 环境负责。

## 3. 算法模块设计

每个算法文件同时包含：

1. 该阶段的抽象接口；
2. 留空的 `Private*` 私有模型适配器；
3. 本模块自己的 `build_test_suite()` 单元测试；
4. 明确的输入和输出 DTO。

算法模块只依赖 `models.py` 中的 DTO 和 `algorithms/base.py`，不依赖 FastAPI、SQLite、Java回调或其他基础设施。

### 3.1 镜头检测

文件：`algorithms/shot_detection.py`

输入：

- `MediaSource`
- `MediaMetadata`
- `AnalysisOptions`

输出：`Sequence[Shot]`

每个 `Shot` 包含 `shot_id`、`start`、`end`、`confidence`。

私有接入类：`PrivateShotDetection`。

### 3.2 音频检测

文件：`algorithms/audio_detection.py`

该模块统一承载：

- ASR；
- VAD；
- 说话人识别；
- 音效、音乐、静音等音频事件。

输出 `AudioAnalysis`，其中包含：

- `transcripts: tuple[TranscriptSegment, ...]`
- `events: tuple[AudioEvent, ...]`

私有接入类：`PrivateAudioDetection`。

### 3.3 OCR检测

文件：`algorithms/ocr_detection.py`

输入视频、媒体信息和镜头列表，输出带时间范围的 `OCRSegment`。私有接入类：`PrivateOCRDetection`。

### 3.4 视觉分析

文件：`algorithms/visual_analysis.py`

输出人物、动作、场景和实体描述 `VisualEvent`。私有接入类：`PrivateVisualAnalysis`。

### 3.5 时间轴融合

文件：`algorithms/timeline_fusion.py`

将镜头、字幕/音频、OCR、视觉结果统一成 `TimelineEvent`。私有接入类：`PrivateTimelineFusion`。

### 3.6 语义分析

文件：`algorithms/semantic_analysis.py`

将时间轴事件转换为主题、人物、地点和事件摘要 `SemanticEvent`。私有接入类：`PrivateSemanticAnalysis`。

### 3.7 剧情分段

文件：`algorithms/plot_segmentation.py`

根据语义事件输出剧情时间区间 `PlotSegment`。私有接入类：`PrivatePlotSegmentation`。

### 3.8 章节生成

文件：`algorithms/chapter_generation.py`

根据剧情区间和语义事件输出 `Chapter`，包含标题、摘要、人物、标签、重要度、剧透等级和缩略图时间。私有接入类：`PrivateChapterGeneration`。

## 4. 私有模型接入规则

接入某个私有模型时只修改对应算法文件，并在 `algorithms/registry.py` 中完成组装。

每个接入实现必须：

- 设置非 `unconfigured` 的 `name` 和 `version`；
- 让 `ready()` 真实反映私有服务状态；
- 将私有模型响应转换为公共 DTO；
- 设置连接、读取和总超时；
- 将鉴权信息放在环境变量或密钥系统，不写入日志；
- 抛出带稳定错误码的异常；
- 不直接访问 SQLite、FastAPI 或 Java 平台；
- 不在模型模块中调用下一个算法模块。

示意依赖方向：

```text
models.py
   ↑
各独立算法模块
   ↑
algorithms/registry.py
   ↑
pipeline.py
   ↑
jobs.py
   ↑
api.py / main.py
```

上层依赖下层契约，算法模块不反向依赖服务层。

## 5. 流水线职责

`pipeline.py` 只负责顺序编排、阶段日志、进度和取消检查，不实现算法。

| 阶段 | 进度 |
|---|---:|
| 来源校验 | 3% |
| 媒体探测 | 8% |
| 镜头检测 | 18% |
| 音频检测 | 30% |
| OCR检测 | 40% |
| 视觉分析 | 52% |
| 时间轴融合 | 62% |
| 语义分析 | 72% |
| 剧情分段 | 82% |
| 章节生成 | 92% |
| 质量校验 | 97% |
| 完成 | 100% |

每个阶段记录：`job_id`、`stage`、开始/结束、耗时、结果数量和异常堆栈。

## 6. 单元测试方式

没有 `tests/` 目录，也没有独立的 `test_*.py`。测试定义和被测算法放在同一个算法文件中，通过 `build_test_suite()` 暴露。

统一执行全部测试：

```powershell
conda activate <你的环境名>
python main.py self-test --all
```

单独测试一个算法模块：

```powershell
python main.py self-test --module shot_detection
python main.py self-test --module audio_detection
python main.py self-test --module ocr_detection
python main.py self-test --module visual_analysis
python main.py self-test --module timeline_fusion
python main.py self-test --module semantic_analysis
python main.py self-test --module plot_segmentation
python main.py self-test --module chapter_generation
```

也可以测试编排层：

```powershell
python main.py self-test --module pipeline
```

流水线测试使用内嵌的确定性 Fake 算法，只验证调用顺序、DTO、进度和最终结构。

## 7. Java 平台 API

视频属于长耗时任务，Java 平台采用异步调用。

### 7.1 创建任务

`POST /api/v1/plot-jobs`

```json
{
  "clientRequestId": "java-order-001",
  "videoUrl": "https://media.example.com/episode.mp4?signature=...",
  "subtitleUrl": null,
  "callbackUrl": "https://java.example.com/callback/plot",
  "options": {
    "language": "zh",
    "profile": "balanced",
    "targetChapterSeconds": 180,
    "spoilerPolicy": "masked"
  }
}
```

支持请求头：

```text
Idempotency-Key: java-order-001
```

### 7.2 接口列表

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health/live` | 服务存活 |
| GET | `/health/ready` | 八个算法模块是否全部就绪 |
| POST | `/api/v1/plot-jobs` | 创建任务 |
| GET | `/api/v1/plot-jobs/{jobId}` | 查询任务 |
| GET | `/api/v1/plot-jobs/{jobId}/result` | 获取结果 |
| POST | `/api/v1/plot-jobs/{jobId}/cancel` | 请求取消 |

私有算法未接入前，`/health/ready` 和创建任务会返回 HTTP 503，不会产生假结果。

### 7.3 Java回调

回调使用：

```text
X-PlotPulse-Timestamp
X-PlotPulse-Signature = HMAC-SHA256(secret, timestamp + "." + body)
```

视频和字幕通过对象存储签名 URL 传递，不通过 API 上传大文件。

## 8. 环境与依赖

项目不创建 `.venv`，直接使用已有 conda 环境：

```powershell
conda activate <你的环境名>
pip install -r requirements.txt
```

运行配置统一从 `config.yaml` 读取，不再使用 `.env.example`：

```yaml
server:
  host: 127.0.0.1
  port: 8000

logging:
  level: INFO

storage:
  database_path: ./data/plotpulse.db

worker:
  max_workers: 1

media:
  ffprobe_bin: ffprobe
  ffprobe_timeout_seconds: 60
  max_video_duration_seconds: 21600
  allow_local_media: false
  allowed_hosts:
    - media.example.com

callback:
  allowed_hosts:
    - java.example.com
  hmac_secret: ""
  timeout_seconds: 10

algorithms:
  shot_detection: {}
  audio_detection: {}
  ocr_detection: {}
  visual_analysis: {}
  timeline_fusion: {}
  semantic_analysis: {}
  plot_segmentation: {}
  chapter_generation: {}
```

默认配置启动：

```powershell
python main.py serve
```

指定其他配置文件：

```powershell
python main.py --config config.local.yaml serve
```

`config.local.yaml` 和 `config.*.local.yaml` 已加入 `.gitignore`，可以存放机器相关配置和密钥；提交到Git的 `config.yaml` 只应包含安全默认值或占位值。

八个 `algorithms.*` 配置段会分别注入对应私有算法实例。当前保持 `{}`，接入模型时再在对应段中增加 `endpoint`、`timeout`、`batch_size` 等该模型实际需要的参数。

当前 Python 依赖：

- FastAPI：HTTP API；
- Pydantic：请求校验；
- Uvicorn：服务启动；
- HTTPX2：API契约测试；
- PyYAML：读取 `config.yaml`；
- SQLite：Python标准库；
- FFmpeg/ffprobe：媒体元数据探测。

私有算法的 SDK、模型参数、GPU要求和服务地址由接入方补入对应算法文件和部署配置。

## 9. 日志

日志采用单行 JSON。至少包含：

- `timestamp`
- `level`
- `event`
- `job_id`
- `stage`
- `progress`
- `elapsed_ms`
- `result_count`
- `error_code`

签名 URL 会删除查询参数。禁止记录 Token、模型密钥、完整字幕和未经脱敏的私有模型响应。

## 10. 迭代计划

### V0.1：框架与算法契约

- 完成八个算法模块拆分；
- 定义模块输入输出 DTO；
- 完成流水线、阶段日志和质量校验；
- 完成同文件单元测试；
- 完成 Java 异步 API 外壳；
- 未接模型时明确返回未就绪。

### V0.2：逐个接入私有模型

建议依次接入：

1. 镜头检测；
2. 音频检测；
3. OCR检测；
4. 视觉分析；
5. 时间轴融合；
6. 语义分析；
7. 剧情分段；
8. 章节生成。

每接入一个模块，先运行本模块自测，再运行 `pipeline` 自测，避免一次接入全部模块后难以定位问题。

### V0.3：效果基线

- 建立人工标注集；
- 统计镜头边界误差；
- 统计字幕/音频时间戳准确率；
- 统计剧情边界人工认可率；
- 统计标题和摘要准确率；
- 记录人工修改率。

### V0.4：准生产

- SQLite替换为PostgreSQL；
- 线程池替换为Redis/RabbitMQ任务系统；
- 中间产物落对象存储；
- 增加断点恢复、重试、熔断和限流；
- Java联调、压测和回调重试；
- Prometheus和OpenTelemetry接入。

### V1.0：生产发布

- GPU Worker独立部署和扩缩容；
- 模型灰度、版本追踪和回滚；
- 权限、审计和配额；
- 运营审核、章节修改、合并和拆分接口。
