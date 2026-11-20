# 学生报销管家

[English](README.en.md)

本地桌面小工具:导入票据照片/扫描件 → 自动识别内容并归类 → 勾选生成正式报销汇总单(.docx / CSV)。

纯本地、零账号、隐私优先:所有数据留在你自己的工作区文件夹,默认不联网、不上传。

## 快速开始

环境:Windows / macOS / Linux,Python 3.11+(Windows 自带 tkinter)。

```bash
pip install -r requirements.txt
python app.py
```

首次启动会弹窗让你选择(或新建)一个工作区文件夹,之后自动记住。

- `python app.py --workspace D:\报销管家` 直接指定工作区
- 安装 `rapidocr-onnxruntime` 后自动启用本地 OCR;不装也能用(见下)

## 使用流程(两步)

1. **导入**:点「添加票据图片」一次多选,或「导入文件夹」批量递归导入,也可以直接把文件拖进窗口。工具会自动读取内容(PDF 电子发票直接抽文字,图片走本地 OCR),识别类别与金额/日期/发票号;识别不了的进入待确认(黄色行)。
2. **汇总**:在列表按日期/类别/关键词筛选,多选即勾选,状态栏实时显示张数与合计;点「统计」可看当前筛选的按类别合计;点「生成汇总单」填报销人信息 → 预览 → 生成 docx(或「导出 CSV」)。

每个自动识别结果都可以在下方编辑面板修正:选中单条 → 改字段 → 「保存」或「确认归档」。**确认时会自动学习"商户→类别"**(借鉴知识本体的学习闭环):比如你确认过一次"汉庭"属于酒店住宿,以后含"汉庭"的票据即使关键词没命中也能自动归类。重复票据(同文件/同发票号/同日期+金额+商户)会标"疑似",可一键「强制保留」。删除只是移入工作区 `.trash/` 回收站。

## 票据格式

图片 `.jpg .jpeg .png .webp .bmp .tif .tiff .gif`,以及 PDF 电子发票(文本型直接抽取内容,连 OCR 都不需要;扫描型自动渲染后走 OCR)。

## OCR(按内容自动归纳)

- 已装 `rapidocr-onnxruntime`(requirements.txt 默认包含):导入时本地识别文字 → 关键词分类(高铁/机票/酒店/网约车/出租车/餐饮)+ 正则提取金额、日期、发票号。
- 未装:回退文件名关键词规则(如文件名含"12306"归高铁),其余进待确认人工处理,**任何情况不阻塞导入**。
- 自动确认的条件:类别识别成功**且识别出金额**;只有日期没有金额的说明类文件会留在待确认队列。
- 也可在「设置」里配置外部 OCR 命令模板(含 `{image}` 占位),显式配置优先于 RapidOCR。

## AI Agent 接入(MCP)

内置一个纯标准库的 MCP 服务器(`mcp_server.py`),让 opencode、Claude Desktop、Cursor 等 AI 客户端用自然语言查询你的票据库、看统计、生成汇总单。LLM 由客户端承担,数据始终在本地。

opencode(`~/.config/opencode/opencode.json`):

```json
{
  "mcp": {
    "baoxiao": {
      "type": "local",
      "command": ["python", "E:\\path\\to\\Invoiceeee\\mcp_server.py"],
      "enabled": true
    }
  }
}
```

Claude Desktop(`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "baoxiao": {"command": "python", "args": ["E:\\path\\to\\Invoiceeee\\mcp_server.py"]}
  }
}
```

注册后在对话框里直接问"9 月的高铁票花了多少""帮我把这几张生成汇总单"即可。工作区解析:环境变量 `BAOXIAO_WORKSPACE` > 上次 GUI 打开的目录。

## 工作区结构

```
工作区/
├── data.db        # SQLite 索引(不存图片)
├── uploads/       # 导入原图(确认归档后会移走)
├── invoices/      # 归档票据:YYYY-MM/类别/YYYYMMDD_商户_金额_编号.图片
├── exports/       # 生成的汇总单与 CSV
├── logs/app.log   # 操作日志(只记动作与元数据)
└── .trash/        # 回收站(删除的票据原图)
```

## 备份与迁移

直接复制整个工作区文件夹即完成备份;换电脑拷过去,`python app.py --workspace 路径` 继续。所有原图都能在 `invoices/` 下按"月份/类别/日期_商户_金额"直接找到。

## 测试

```bash
python -m unittest discover -s tests -v   # 单元与管线测试
python tools/smoke_gui.py                 # GUI 全流程自动冒烟
```

## 示例

`samples/` 内含完整示例工作区与一份生成的汇总单样例;`python tools/make_samples.py` 可重新生成。

## 已知限制

- HEIC(iPhone 原生格式)暂不支持,请先转换为 JPG。
- 重复检测为精确匹配(哈希/发票号/日期+金额+商户),不做模糊相似度。
- 单机单人使用;无账号、无同步、无云服务。
- 金额两位小数;不生成大写金额;汇总单不嵌票据缩略图。
- GUI 未经自动化测试覆盖界面交互(逻辑层有 71 个测试 + 冒烟脚本)。

## 项目状态

P0(含 GUI 升级)已完成,项目收尾,不欠维护。
