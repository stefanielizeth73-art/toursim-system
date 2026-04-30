# 项目目录说明

当前目录按照“运行入口、业务数据、页面资源、脚本工具、说明文档”来组织，便于后续继续做路线规划和图数据管理。

```text
toursim_system/
├── app.py                        # Flask 主入口
├── init_db.py                    # 数据库初始化
├── requirements.txt              # 依赖列表
├── render.yaml                   # Render 部署配置
├── README.md                     # 项目说明
│
├── data/                         # 运行时数据
│   ├── places.csv                # 景点/校园主数据
│   ├── foods.csv                 # 美食数据
│   ├── facilities.csv            # 设施数据
│   ├── route_graph.json          # 当前内部路线图
│   ├── generated/                # 脚本生成的候选数据
│   ├── raw/                      # 原始接口返回数据
│   └── legacy/                   # 遗留测试文件
│
├── templates/                    # Jinja 页面模板
├── static/                       # 样式和前端交互脚本
│
├── scripts/
│   ├── data/                     # 数据扩充、抓取、图构建脚本
│   └── share/                    # 临时公网分享脚本
│
├── docs/                         # 项目说明文档
│   ├── deployment/               # 部署相关文档
│   ├── project_structure.md      # 当前目录说明
│   ├── module_sequence.md        # 按 PPT 顺序推进模块
│   ├── data_and_graph_pipeline.md# 数据爬取与图网络方案
│   └── recommendation_module.md  # 第一部分：旅游推荐说明
│
├── tourism.db                    # SQLite 数据库
├── venv/                         # 本地虚拟环境
└── .vscode/                      # 编辑器配置
```

## 当前整理原则

- 根目录只保留运行入口、部署配置和最核心说明文件。
- 所有数据加工脚本统一放到 `scripts/data/`。
- 所有临时分享脚本统一放到 `scripts/share/`。
- 所有说明性材料统一放到 `docs/`。
- 运行中真正会被 Flask 读取的数据，仍然保留在 `data/` 顶层，避免改动过大。

## 对后续路线规划的好处

- 我们后面新增“多景点内部图”时，可以继续把候选图放进 `data/generated/`，校对后再合并进正式数据。
- 如果要为不同校园/景区建立多张图，下一步可以在 `data/graphs/` 下扩展，不会和现有脚本冲突。
- 路线规划脚本、设施映射脚本、图清洗脚本都可以继续收进 `scripts/data/`，不会再把根目录挤乱。
