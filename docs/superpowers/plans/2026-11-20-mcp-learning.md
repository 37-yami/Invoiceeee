# MCP + 学习规则 计划(2026-11-20)

> 灵感来源:NVIDIA/auto-ontology(理念借鉴,不引代码;平台本身与项目气质冲突,不接入)

**Feature A:商户学习规则(它的 "Learn" 理念)**
- 新表 `learned_rules(keyword TEXT PRIMARY KEY, category TEXT, hits INTEGER)`,init_schema 幂等建表(旧工作区向后兼容)
- 学习时机:任何"确认归档"且商户非空 → upsert (归一化商户 → 类别),hits 累加
- 应用时机:导入识别时,学习规则优先级介于"用户显式选择"与"关键词规则"之间(置信 0.9):
  匹配方式 = 归一化商户名是否出现在新票据文本(去空白)中
- 新模块 `core/learned.py`:learned_upsert(db, merchant, category) / learned_lookup(db, squashed_text)
- 测试:upsert/lookup、冲突后写、导入集成(确认"汉庭"后,新文本含"汉庭"自动归类)

**Feature B:极简 MCP 服务器(它的 "Expose" 理念)**
- 新文件 `mcp_server.py`(仓库根,纯标准库):newline-delimited JSON-RPC 2.0 over stdio
- 工具:`query_invoices(status?, category?, date_from?, date_to?, q?)`、`stats()`、`generate_report(ids, meta?)`
  generate_report 写入 exports/ 并返回绝对路径;query 只回元数据字段(不含路径,防泄露)
- 工作区解析:环境变量 `BAOXIAO_WORKSPACE` > ~/.student_invoice_gui.json 记忆值
- 测试:子进程管道喂 JSON-RPC(initialize → tools/list → tools/call)断言响应
- README(中英)给出 opencode / Claude Desktop 注册片段

**验证:** 全量测试绿;冒烟不回归;真实发票脚本重跑;推送。
