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
