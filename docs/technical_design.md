# Technical Design Notes
This document consolidates the former module sequence, data/graph pipeline, and recommendation module notes for handoff.

---

## Module Sequence

_Source before consolidation: `docs/module_sequence.md`_

# 按 PPT 顺序推进模块

本项目按课程设计 PPT 的功能顺序逐步完善。每个阶段先完成可演示功能，再补充数据规模和算法说明。

## 1. 旅游推荐

目标：完成旅游前目的地选择，包括景点/校园查询、兴趣标签推荐、热度与评分排序。

数据：
- `data/places.csv`：系统实际读取的景点/校园数据。
- `scripts/data/place_seeds.csv`：待爬取的景点/校园种子名单。
- `data/generated/places_crawled.csv`：脚本生成的候选数据。

算法：
- 查找：名称、类别、标签、关键字匹配。
- 排序：评分、热度、综合推荐分。
- Top-K：后续应将完全排序改成小根堆或快速选择，体现“只取前 10 个”的课程要求。

推进动作：
- 先把 `place_seeds.csv` 扩到 200 个地点。
- 运行 `scripts/data/fetch_places.py` 批量补充经纬度和 OSM 标识。
- 人工校对后再合并到 `data/places.csv`。

## 2. 旅游路线规划

目标：完成进入景区/校园后的路线规划，包括单目标最短路径、多目标往返路径、最短距离与最短时间策略。

数据：
- `data/graphs/xmu_manual.json`：当前正式路线图，由手动采集数据自动生成。
- `data/manual/xmu_collector_nodes.json`：手动采集的 POI 和道路节点草稿。
- `data/manual/xmu_collector_edges.json`：手动采集的道路折线草稿。
- 后续可扩展为 `data/graphs/<place_id>.json`，实现一个景点/校区对应一张图。

算法：
- 图存储：邻接表。
- 单目标路径：Dijkstra。
- 多目标路径：小规模目标点枚举；后续可优化为动态规划或启发式算法。
- 时间策略：边权由距离、拥挤度、交通方式共同决定。

推进动作：
- 对 1 到 3 个重点地点构建真实道路图。
- 校对道路节点、建筑物入口、不可通行路径。
- 将图切换接入页面选择逻辑。

## 3. 场所查询

目标：在景区/校园内部查询卫生间、商店、超市、图书馆、咖啡点等设施，并按道路距离排序。

数据：
- `data/facilities.csv`：当前演示设施数据。
- `data/generated/facilities_<地点>.csv`：从 OSM 生成的候选设施。

算法：
- 查找：设施类别和关键字过滤。
- 排序：基于图上最短路径距离排序，避免使用直线距离。

推进动作：
- 先复用路线规划阶段生成的道路图。
- 将爬取到的设施映射到最近道路节点。
- 人工补齐 OSM 缺失的校园特色设施。

## 4. 旅游日记管理

目标：完成旅游后的日记发布、浏览、评分、检索与推荐。

数据：
- SQLite `diaries` 表：存储标题、目的地、正文、作者、浏览量、评分。

算法：
- 查找：标题、目的地、正文全文检索。
- 排序：浏览热度、平均评分、发布时间。
- 后续扩展：倒排索引、哈夫曼压缩、多媒体索引。

推进动作：
- 补日记编辑/删除权限。
- 增加点赞字段和图片字段。
- 做全文检索和压缩算法演示。

## 5. 旅游日记交流与 AIGC

目标：围绕日记内容做交流和智能生成。

算法与能力：
- 精确查询：日记标题索引。
- 全文检索：倒排索引。
- 无损压缩：文本压缩算法。
- AIGC：根据文字和图片生成摘要、游记文案或短视频。

推进动作：
- 先完成文本检索与排序。
- 再加入图片上传和存储。
- 最后将 AIGC 作为创新功能接入。

## 6. 美食推荐

目标：根据景点/校园、菜系、距离、评分、热度和消费水平推荐美食。

数据：
- 正式入口基于路线规划图：`data/graphs/xmu_manual.json`，通过 `load_route_graph()` 复用自动重建和 Dijkstra 图结构。
- 已采集但尚未完全建成“场所”的餐饮候选，会从 `data/manual/xmu_collector_facilities.json` 中 `type=餐饮` 的采集设施进入美食系统；旧 `xmu_xiang_an` 候选入口保留兼容。
- 前期测试用的全局 `data/foods.csv` 已移除。

算法：
- 模糊查找：名称、菜系、窗口/饭店名称、说明、来源。
- 菜系细分：根据店名自动识别东北菜、川菜、湘菜、火锅、自助、烧烤、奶茶等类型，采集端也可手动选择。
- 自定义菜系：采集端选择“其他餐饮”时可手动输入新菜系，新菜系会作为 `cuisine` 写入并进入美食页分类。
- 排序：评分、热度、距离、综合分；距离起点可从路线图点击选择。
- Top-K：只取前 10 个美食结果。

推进动作：
- 已将美食推荐正式指向翔安校区手动采集路线图。
- 路线规划页已显示与当前起点关联的美食窗口，并可一键设为路线终点。
- 美食页改为信息流卡片展示，不再把“所属地点”作为主列表字段。
- 后续采集完成后，`餐饮` 标签设施会随路线图自动进入距离排序和 Top-K 推荐。


---

## Data And Graph Pipeline

_Source before consolidation: `docs/data_and_graph_pipeline.md`_

# 数据爬取与图网络构建方案

## 数据源选择

路线规划模块当前采用“手动采集 + 自建图”的方案。高德地图只作为可视化底图和采集画布，POI 与道路折线由用户在地图上点击确认后保存到本地 JSON，再由系统生成 `nodes/edges` 图结构。

这样做的好处是：图中每个地点、每条路都可解释、可修改，避免自动地图数据与校园实际标注不一致。

## 图网络设计

内部地图抽象为图 `G=(V,E)`。

节点 `V`：
- 路口节点：道路交叉点或道路折点。
- 建筑节点：教学楼、图书馆、食堂、博物馆等。
- 设施节点：卫生间、商店、超市、咖啡点、服务站等。

边 `E`：
- 表示真实可通行道路。
- `distance` 表示道路长度。
- `congestion` 表示拥挤度。
- `walk`、`bike` 表示交通方式是否可用。

当前系统使用邻接表读取图数据，再由 Dijkstra 计算单目标最短路径。场所查询也复用这张图，把设施挂到最近道路节点，再按图上路径距离排序。

## 脚本流程

### 1. 扩充宏观景点/校园数据

先编辑：

```powershell
scripts/data/place_seeds.csv
```

再运行：

```powershell
python scripts/data/fetch_places.py --limit 20
```

输出：

```text
data/generated/places_crawled.csv
data/raw/nominatim/
```

确认数据无误后，可以把 `places_crawled.csv` 合并到 `data/places.csv`。

### 2. 构建单个景区/校园内部图

打开采集页面：

```text
http://127.0.0.1:5005/route?collect=1
```

采集数据保存到：

```text
data/manual/xmu_collector_nodes.json
data/manual/xmu_collector_edges.json
data/manual/xmu_collector_meta.json
```

后台会自动重建正式图：

```text
data/graphs/xmu_manual.json
```

## 人工校对规则

爬取数据不能直接等于最终数据。课程设计验收更关注“数据结构与算法如何服务业务”，所以建议保留人工校对步骤。

重点检查：
- 路口是否连通。
- 建筑入口是否挂到可达道路节点。
- 卫生间、商店、食堂等设施是否类别正确。
- 边数是否达到课程要求。
- 是否存在明显跨湖、穿墙、穿建筑的错误道路。

## 后续接入方向

当前路线模块默认读取 `data/graphs/xmu_manual.json`，其原始采集草稿保存在 `data/manual/xmu_collector_*`。如果后续要扩展到多个景区/校园，可以继续沿用同样结构：

```text
data/graphs/
├── place_1.json
├── place_2.json
└── place_3.json
```

页面上先选择景点/校园，再加载对应图。这样就能同时支持多个景区和校区的内部路线规划。

## 厦门大学翔安校区手动采集流程

翔安校区当前正式图位于：

```text
data/graphs/xmu_manual.json
```

它只包含手动采集数据：

- 手动 POI：校门、图书馆、食堂、宿舍、教学楼等可选择节点。
- 手动道路：沿高德底图点击采集的道路折线。
- 自动图生成：后台把道路折线拆成 road 节点和 edge。

高德只用于显示底图；最终路线仍由项目自己的邻接表和 Dijkstra 算法计算。

### 1. 配置高德 JS Key

在本地 `.env` 中添加或确认：

```powershell
AMAP_JS_KEY=你的高德JSKey
AMAP_SECURITY_JS_CODE=你的安全密钥
```

`.env` 已被 `.gitignore` 忽略，不要把真实 Key 写入仓库文件。

### 2. 采集 POI 和道路

打开路线页并启用编辑模式：

```text
http://127.0.0.1:5005/route?collect=1
```

POI 模式点击地图保存地点；道路模式沿路连续点击，双击保存道路。保存后后台自动重建正式图。

### 3. 验证图结构

刷新 `/route`，选择已采集的起点和终点。若 Dijkstra 可以返回路径，说明对应道路已经连通。


---

## Recommendation Module

_Source before consolidation: `docs/recommendation_module.md`_

# 旅游推荐模块说明

## 模块目标

旅游推荐对应 PPT 的第一部分，服务于“旅游前”的目的地选择。用户可以根据名称、城市、类别、兴趣标签查询景点/校园，也可以根据热度、评分和兴趣标签生成 Top-K 推荐结果。

## 数据设计

当前主数据文件：

```text
data/places.csv
```

当前演示数据规模为 280 条，其中校园 140 条、景区 140 条，覆盖 40+ 个城市，满足课程设计中“景区和校园数量至少 200 个”的数据规模要求。

扩容脚本 `scripts/data/expand_demo_places.py` 默认采用追加模式：保留 `data/places.csv` 中现有行的所有人工修改，只在数量不足时补新条目；只有显式使用 `--rebuild` 参数时，才会从基础种子重新生成。脚本也支持 `--file` 参数，便于先在副本上验证再应用到正式数据。

字段说明：

```text
id            唯一编号
name          景点或校园名称
type          类型，景区/校园
city          所在城市
rating        评分
popularity    热度
tags          兴趣标签，使用分号分隔
description   简介
```

候选数据爬取：

```powershell
python scripts/data/fetch_places.py --limit 20
```

脚本会读取：

```text
scripts/data/place_seeds.csv
```

并生成：

```text
data/generated/places_crawled.csv
```

生成数据需要人工校对后再合并到 `data/places.csv`。这样可以避免公开地图接口返回的名称、边界或分类不准确时直接影响演示。

## 查询功能

地点列表页支持：

- 名称、城市、简介关键字检索。
- 标签检索，多个标签可以用分号分隔。
- 类型过滤：景区、校园。
- 城市过滤。
- 按评分或热度升序/降序排序。

## 推荐算法

基础推荐分：

```text
base_score = rating * 60 + popularity * 0.4
```

个性化推荐分：

```text
recommend_score = base_score + matched_interest_tags * 15
```

Top-K 实现：

- 扫描所有候选地点。
- 对符合城市和类型过滤条件的地点计算推荐分。
- 使用小根堆维护当前分数最高的 K 个地点。
- 最后只对堆中的 K 个结果排序并展示。

该设计符合 PPT 中“用户通常只看前 10 个景点或者学校，要求不经过完全排序可以排好前 10”的要求。时间复杂度为 `O(n log k)`，当 `k` 远小于 `n` 时，比完整排序 `O(n log n)` 更适合大规模数据。

## 下一步完善

- 将 `scripts/data/place_seeds.csv` 扩展到 200+ 个景点/校园。
- 合并并校对 `data/generated/places_crawled.csv`。
- 增加用户画像表，保存用户长期兴趣标签。
- 增加推荐权重配置，让评分、热度、兴趣标签的影响可调。
