# 数据爬取与图网络构建方案

## 数据源选择

本项目优先使用 OpenStreetMap 生态的数据源。

- Nominatim：用于将景点/校园名称解析为经纬度、边界和 OSM 标识。
- Overpass API：用于按区域抓取道路、建筑物、服务设施和兴趣点。
- OSMnx：后续可选，用于更方便地从 OSM 构建道路图；当前脚本先使用 Python 标准库实现，减少依赖。

使用公开接口时要控制频率。Nominatim 适合少量地名解析；批量道路、建筑和设施数据应使用 Overpass。

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

示例：

```powershell
python scripts/data/build_osm_graph.py --place "北京邮电大学沙河校区, 北京, 中国" --max-edges 300
```

输出：

```text
data/generated/route_graph_北京邮电大学沙河校区_北京_中国.json
data/generated/facilities_北京邮电大学沙河校区_北京_中国.csv
data/raw/overpass/
```

确认道路图和设施映射合理后，可以替换或合并到：

```text
data/route_graph.json
data/facilities.csv
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

当前系统只读取单个 `data/route_graph.json`。路线模块进一步完善时，可以改为：

```text
data/graphs/
├── place_1.json
├── place_2.json
└── place_3.json
```

页面上先选择景点/校园，再加载对应图。这样就能同时支持多个景区和校区的内部路线规划。
