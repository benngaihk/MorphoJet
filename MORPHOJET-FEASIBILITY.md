# MorphoJet 可行性报告

**日期:** 2026-07-01  
**建议项目名:** **MorphoJet**  
**一句话定位:** CellProfiler-compatible 的高速细胞/组织图像测量引擎，先做批量测量的 drop-in 子集，而不是重写完整 GUI 生态。

## 0. 结论

**建议立项，但必须收窄范围。**

不要重写 ImageJ/Fiji、CellProfiler、QuPath 或 napari 这类完整生态。第一阶段只做一个可验证、可传播、可替换的窄切口：

> 输入显微图像 + 已有 segmentation mask / label image，输出与 CellProfiler `ExportToSpreadsheet` 可对齐的 per-image / per-object measurements CSV。

这个切口和 `gxfkit` 的成功逻辑一致：旧工具作为 oracle，公开语料作为 benchmark，输出可 diff，性能可复现，先用一个小而准的子集打出可信度。

**推荐 M0 gate:**

- 正确性：核心 measurement 与 CellProfiler headless 输出达到 >=99% 数值一致，浮点误差设定公开 tolerance。
- 性能：在 1k-10k 张 2D 多通道显微图像上 >=10x wall-clock speedup。
- 内存：批量处理大 TIFF/OME-TIFF 时 RSS 至少低于 CellProfiler 50%。
- 复现：`benchmark/run.sh` 一键跑 CellProfiler、MorphoJet、diff 和性能表。
- 传播：第一篇文章标题就是可验证结论，而不是愿景。

## 1. 为什么不是 ImageJ，而是 CellProfiler-compatible measurement

你身边做生信、组学和显微图像的老师，大概率会碰到这些软件：

| 方向 | 常见软件 | 适不适合被新项目替代 | 判断 |
|---|---|---:|---|
| 通用显微图像 | ImageJ / Fiji | 低 | 太像操作系统和插件生态，替代面太大，不适合作为第一枪。 |
| 批量图像定量 | CellProfiler | 高 | pipeline + images -> measurements，天然可做 oracle 和 benchmark。 |
| 数字病理 | QuPath | 中 | 影响力强，但 WSI、交互、标注和脚本生态复杂，适合作为 M3+ 场景。 |
| 交互式 ML segmentation | ilastik | 低 | 核心价值在交互训练，不是简单文件转换或测量。 |
| Python 图像查看/插件 | napari | 低 | 是平台，不是单一旧工具。 |
| 深度学习分割 | Cellpose / StarDist | 中 | 可作为上游 mask 生成器，不建议 M0 直接挑战算法准确率。 |

CellProfiler 的优势是用户真实、格式稳定、输出明确。它的短板也清楚：headless/batch 运行需要安装完整 Python/GUI 依赖，批处理经常要用户自己切 job，大规模图像时速度和内存体验不够轻。

MorphoJet 的正确定位不是“替代 CellProfiler”，而是：

> CellProfiler 继续负责 GUI、pipeline authoring 和完整生态；MorphoJet 负责把已经稳定的 measurement pipeline 在服务器/工作站上跑得更快、更容易部署。

## 2. 已有项目与竞争格局

### 2.1 直接 oracle：CellProfiler

CellProfiler 是最重要的对照组，不是敌人。它负责定义行为和输出。M0 必须把它当作正确性基准：

- 使用 CellProfiler 官方 example pipelines 和公开图像数据。
- 固定 CellProfiler 版本。
- 保存原始 output CSV。
- 所有差异进入 `PARITY.md`，分成 `GAP`、`EQUIV`、`FIX`。

### 2.2 直接竞争：cp_measure

`cp_measure` 已经明确提出“复现 CellProfiler 测量”的方向，说明赛道不空白。它对 MorphoJet 的含义是双重的：

- 正面：需求真实，CellProfiler measurement 子集值得被单独加速。
- 风险：如果 MorphoJet 只是“另一个 Python measurement 包”，没有传播价值。

MorphoJet 必须避开它的正面战场，主打：

- 一进制 CLI / Rust core / 易部署。
- benchmark-first，而不是 API-first。
- CellProfiler parity ledger。
- 高通量批处理和集群友好。
- Python binding 放在 M2，不作为 M0 核心卖点。

### 2.3 性能竞争：Nyxus

Nyxus 是高性能图像 feature extraction 项目，和 CellProfiler/ImageJ/scikit-image 的 feature extraction 场景重叠。它说明“高速 feature extraction”已经有人做，MorphoJet 不能只喊快。

差异化要放在：

- CellProfiler-compatible 输出。
- 对老师已有 `.cppipe` / CSV 工作流友好。
- Benchmark 直接回答“我现在的 CellProfiler pipeline 能不能替换”。

### 2.4 实验室熟悉对照：Fiji/ImageJ

ImageJ/Fiji 不作为主要 oracle，但适合作为传播对照：

- `Analyze Particles` / macro batch 是很多老师和学生熟悉的路径。
- 可以在文章里放一个“传统 Fiji macro vs CellProfiler vs MorphoJet”的小表。
- 不追求 ImageJ 全兼容，只做少数测量指标对照。

### 2.5 Python baseline：scikit-image + pandas

这是工程对照组，证明 MorphoJet 不只是“比 GUI 软件快”，也比常见 Python 脚本更稳：

- `skimage.measure.regionprops_table`
- pandas CSV export
- Dask/Joblib 并行版本可作为高级 baseline

## 3. 产品定义

### 3.1 M0 支持范围

**只做已有 mask 的测量，不做 segmentation。**

输入：

- 2D grayscale / multichannel TIFF。
- label mask / segmentation mask。
- image table CSV：image path、mask path、channel name、metadata。

输出：

- `Image.csv`
- `Objects.csv`
- 可选 `Experiment.csv`
- 与 CellProfiler `ExportToSpreadsheet` 命名尽量对齐。

M0 measurement：

- `MeasureImageIntensity`
- `MeasureObjectIntensity`
- `MeasureObjectSizeShape`
- object count / area / centroid / bounding box
- min / max / mean / median / integrated intensity
- basic shape descriptors：perimeter、eccentricity、solidity、major/minor axis

M0 不做：

- GUI。
- full `.cppipe` parser。
- segmentation / threshold / illumination correction。
- 3D volume。
- WSI whole-slide streaming。
- tracking。
- deep learning inference。

### 3.2 命令草案

```bash
morphojet measure \
  --images images.csv \
  --out measurements/ \
  --threads 16 \
  --cellprofiler-compatible
```

`images.csv` 示例：

```csv
ImageNumber,ImagePath,MaskPath,Channel,Plate,Well,Site
1,images/A01_s1_DAPI.tif,masks/A01_s1_cells.tif,DAPI,P001,A01,1
2,images/A01_s1_CD3.tif,masks/A01_s1_cells.tif,CD3,P001,A01,1
```

## 4. 可量化评估设计

### 4.1 正确性指标

| 指标 | M0 gate | 说明 |
|---|---:|---|
| object count parity | 100% | 同一 mask 下 object 数必须一致。 |
| area / centroid parity | >=99.9% | 整数或半像素规则必须公开。 |
| intensity feature parity | >=99% | 浮点 tolerance：默认 abs <=1e-6 或 rel <=1e-5。 |
| CSV schema compatibility | >=95% | 优先兼容 CellProfiler 常用列名。 |
| pipeline-level pass rate | >=90% | 官方 example + 自建 benchmark pipelines。 |

### 4.2 性能指标

| 指标 | M0 gate | 说明 |
|---|---:|---|
| wall-clock speedup | >=10x | vs CellProfiler headless，同机同数据。 |
| peak RSS | <=50% of CellProfiler | 用 `/usr/bin/time -v` 或 container stats。 |
| throughput | images/minute | 按 1、4、8、16 threads 画 scaling。 |
| cold start | <=1s | 一进制 CLI 的安装和启动优势要量化。 |
| output write speed | >=5x | 大 CSV 输出不能成为瓶颈。 |

### 4.3 对照项目组

| 组别 | 工具 | 角色 | 评价内容 |
|---|---|---|---|
| Oracle | CellProfiler headless | 正确性基准 | CSV parity、pipeline behavior、耗时/RSS |
| Direct competitor | cp_measure | 同类 measurement engine | feature 覆盖、速度、安装体验 |
| High-performance feature extraction | Nyxus | 高性能基准 | feature 覆盖、吞吐、并行扩展 |
| Lab baseline | Fiji/ImageJ macro | 老师熟悉路径 | 少数指标 sanity check、易用性对比 |
| Python baseline | scikit-image + pandas | 常见脚本路径 | 速度、内存、代码复杂度 |

### 4.4 数据集

M0 数据集要遵循“公开、可下载、可复现、大小分层”：

- Tiny smoke：10-50 张小图，用于 CI。
- Medium benchmark：1k 张 2D 多通道图，用于每次 release。
- Large benchmark：10k+ 张图或合成放大数据，用于宣传文章。
- 真实公开数据：优先选 CellProfiler tutorials / examples、Broad Bioimage Benchmark Collection、Cell Painting/JUMP 子集。

## 5. 里程碑

### M-1：靶点验证，1 周

目标：确认项目不是伪需求。

- 选 3 个真实 CellProfiler pipeline。
- 跑通 CellProfiler headless。
- 导出 CSV。
- 手写一个最小 Python/NumPy baseline，估算速度上限。
- 写 `docs/FEASIBILITY.md` 和 benchmark plan。

Gate：

- CellProfiler baseline 可复现。
- 至少一个 pipeline 的耗时 >=10 分钟，且 measurement 阶段占比明显。

### M0：最小可打穿版本，3-4 周

目标：做出第一个可以公开 benchmark 的 CLI。

- Rust workspace：`morphojet-core` + `morphojet` CLI。
- TIFF/OME-TIFF 基础读取。
- label mask 遍历。
- intensity + size/shape 核心 features。
- CSV writer。
- CellProfiler output normalizer。
- `benchmark/run.sh`：CellProfiler vs MorphoJet。
- `docs/PARITY.md`：所有差异公开记录。

Gate：

- 1k 张图 >=10x faster。
- 核心 features >=99% parity。
- README 有可复现表格。

### M1：真实实验室可试用，4-6 周

目标：让身边老师可以拿一批图试。

- 支持多通道、plate/well/site metadata。
- 支持 CellProfiler-style input table。
- 增加常用 morphology features。
- 改善 error reporting。
- 发布 macOS/Linux binaries。
- 提供 Python wheel 只做 wrapper。

Gate：

- 3 个真实用户数据集跑通。
- 每个数据集都有 CellProfiler parity report。
- 安装不需要完整 CellProfiler 环境。

### M2：生态入口，6-8 周

目标：不只是 CLI，而是进入常见工作流。

- Snakemake wrapper。
- Nextflow module。
- napari plugin：只做结果查看，不做全 GUI。
- CellProfiler plugin/export bridge：从 CellProfiler pipeline 导出 MorphoJet config。
- 文档：从 CellProfiler pipeline 迁移的 cookbook。

Gate：

- 至少一个老师的真实 workflow 可以替换 measurement stage。
- 有 1 篇英文 technical blog + 1 篇中文案例文章。

### M3：扩大护城河，2-3 个月

目标：从“快的玩具”变成“可信工具”。

- 3D volume measurements。
- OME-Zarr / tiled TIFF streaming。
- WSI tile mode。
- GPU 可选加速，仅在 CPU 版稳定后做。
- JOSS / Bioinformatics Application Note。

Gate：

- 5+ public benchmark datasets。
- 20+ pipelines / feature groups 有 parity ledger。
- 有外部用户 issue / PR / citation。

## 6. 宣传策略

### 6.1 核心叙事

不要说：

> We rewrote CellProfiler in Rust.

要说：

> CellProfiler is the oracle. MorphoJet is the fast batch measurement engine for stable pipelines.

中文叙事：

> CellProfiler 负责定义正确答案，MorphoJet 负责把大批量测量跑快。

### 6.2 第一篇文章

标题候选：

- `MorphoJet: 10-50x faster CellProfiler-compatible measurements for microscopy screens`
- `CellProfiler is right. Batch measurement can still be much faster.`
- `把 CellProfiler 批量测量从数小时压到数分钟：一个可复现的 Rust 子集`

文章结构：

1. 老师/学生真实痛点：GUI pipeline 做好了，但服务器批量跑慢。
2. 为什么不替代 CellProfiler：尊重 oracle。
3. Benchmark command：一键复现。
4. CSV parity：哪些完全一致，哪些有浮点差异。
5. 速度/RSS 表。
6. 如何试用：下载二进制，一条命令跑。
7. Roadmap：feature coverage 和用户数据集征集。

### 6.3 发布渠道

优先：

- image.sc forum。
- CellProfiler forum / GitHub discussion。
- rust-bio / bioinformatics Slack。
- Twitter/X + LinkedIn 短 benchmark 图。
- 你身边老师的真实案例，匿名也可以。

第二层：

- JOSS。
- Bioinformatics Application Note。
- Open Microscopy / OME 社区。
- napari / scverse 周边社区。

### 6.4 README 第一屏

README 第一屏必须包括：

- 一句话定位。
- CellProfiler-compatible，不说 full replacement。
- benchmark 表。
- parity 表。
- 一条安装命令。
- 一条运行命令。
- “What is not supported yet”。

### 6.5 声量打法

真正打响知名度的不是“项目开源”，而是连续 3 次可验证发布：

| 发布 | Headline | 目的 |
|---|---|---|
| v0.1 | 10x faster on official tutorials, >=99% parity | 证明不是 PPT。 |
| v0.2 | 10k images benchmark, low memory, binaries | 证明可用。 |
| v0.3 | Real lab case study, Snakemake/Nextflow | 证明有人需要。 |

## 7. 风险与缓解

| 风险 | 严重度 | 缓解 |
|---|---:|---|
| CellProfiler feature 细节很多，完全兼容很难 | 高 | 只承诺 measurement 子集；所有差异写入 parity ledger。 |
| cp_measure / Nyxus 已经占位 | 高 | 主打 CLI、CellProfiler oracle、低安装摩擦、benchmark-first。 |
| 图像格式复杂 | 中 | M0 只支持常见 TIFF；OME-Zarr / WSI 放 M3。 |
| segmentation 算法争议大 | 高 | M0 完全不做 segmentation，只消费 mask。 |
| 用户不愿迁移 | 中 | 做 CellProfiler export bridge，让迁移成本接近一条命令。 |
| 浮点差异引发不信任 | 中 | tolerance 公开，feature-by-feature report，保留 CellProfiler 原始输出。 |

## 8. 技术路线

建议栈：

- Rust core：并行遍历、feature accumulation、CSV writer。
- `rayon`：CPU parallelism。
- `image` / `tiff` / `ndarray`：M0 基础图像处理。
- 后续接 `ome-types` / OME-Zarr。
- Python binding：`pyo3` + `maturin`，M1 后再做。

核心数据结构：

- `ImageTable`
- `LabelImage`
- `ObjectAccumulator`
- `FeatureSet`
- `MeasurementTable`
- `ParityReport`

性能关键点：

- 对 label mask 单次扫描，同时累计 area、bbox、sum、min、max。
- 对多通道图像共享 object index。
- 避免 per-object Python object / pandas 中间态。
- CSV streaming writer。
- 线程级 image parallel，必要时 tile parallel。

## 9. 是否值得做

**值得，但条件是：**

1. 不重写 CellProfiler。
2. 不做 segmentation。
3. 不做 GUI。
4. 不和 Nyxus 比“feature 数量最多”。
5. 只用 CellProfiler parity + 高通量批处理 + 低安装摩擦打第一枪。

如果 M0 跑不出 >=10x 或 parity 做不到 >=99%，应立刻停，不要陷入“大而全图像平台”。

如果 M0 成功，这个项目比 `gxfkit` 更容易进入你身边老师的真实 workflow，因为显微图像批量测量的等待时间更直观，demo 更容易展示。

## 10. 推荐仓库结构

```text
morphojet/
  crates/
    morphojet-core/
    morphojet/
  benchmark/
    Dockerfile
    run.sh
    summarize.py
  corpus/
    download.sh
  tests/
    parity/
      normalize_measurements.py
  docs/
    DESIGN.md
    ROADMAP.md
    PARITY.md
    M0-REPORT.md
  README.md
```

## 11. 信息源

- CellProfiler GitHub: <https://github.com/CellProfiler/CellProfiler>
- CellProfiler project site: <https://cellprofiler.org/>
- CellProfiler command-line guide: <https://carpenter-singh-lab.broadinstitute.org/blog/getting-started-using-cellprofiler-command-line>
- CellProfiler batch guide: <https://carpenter-singh-lab.broadinstitute.org/blog/getting-started-cellprofiler-batch>
- CellProfiler modules documentation: <https://cellprofiler-manual.s3.amazonaws.com/CellProfiler-4.2.1/modules/measurement.html>
- Broad Bioimage Benchmark Collection: <https://bbbc.broadinstitute.org/>
- cp_measure paper / package: <https://arxiv.org/html/2507.01163v1>
- Nyxus: <https://github.com/PolusAI/nyxus>
- Fiji/ImageJ: <https://fiji.sc/>
- QuPath: <https://qupath.github.io/>
- ilastik: <https://www.ilastik.org/>
- napari: <https://napari.org/>
- scikit-image regionprops: <https://scikit-image.org/docs/stable/api/skimage.measure.html#skimage.measure.regionprops_table>
