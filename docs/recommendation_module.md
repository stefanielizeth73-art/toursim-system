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
