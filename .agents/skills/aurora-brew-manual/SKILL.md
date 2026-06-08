---
name: aurora-brew-manual
description: 阅读虚构产品“幻曜萃饮仪 HX-1（Aurora Brew）”附带的说明书，并回答关于安装、配件、规格、冲煮模式、清洁、保养、安全提示和故障码的问题。当用户提到“幻曜萃饮仪”、Aurora Brew、HX-1、产品说明书、使用说明、参数、清洁、保养、故障码，或要求查询该产品说明书细节时使用。
---

# 幻曜萃饮仪说明书检索

使用此 skill 回答虚构产品“幻曜萃饮仪 HX-1”相关的说明书问题。
优先依据随 skill 提供的参考资料回答，不要补充说明书中未出现的规格、安全结论或维修建议。

## 适用场景示例

- 幻曜萃饮仪怎么开机
- 帮我查一下 Aurora Brew 的清洁步骤
- HX-1 的容量和额定功率是多少
- 这台机器报 E03 是什么意思
- 读取一下幻曜萃饮仪的产品说明书

## 关键词提示

- 幻曜萃饮仪 / Aurora Brew / aurora brew / HX-1 / hx-1
- 产品说明书 / 使用说明 / 参数 / 清洁 / 保养 / 故障码

## 工作流

1. 先确认问题确实围绕“幻曜萃饮仪 HX-1”或 “Aurora Brew” 的说明书内容。
2. 优先使用 `read_file` 读取 [`references/product-manual.md`](references/product-manual.md)。
3. 仅当需要全文返回或做关键词检索时，再执行 [`scripts/read_manual.py`](scripts/read_manual.py)。
4. 回答时先给结论，再补充对应步骤、参数、警示或故障码细节。
5. 如果说明书中没有该信息，明确说明“当前说明书未提供该信息”。

## 输出要求

- 回答使用中文。
- 当用户问具体参数、步骤、告警或故障码时，优先给出说明书里的精确信息。
- 当用户问概览时，可以先做简洁总结，再补关键细节。

## 资源

- 参考说明书：[`references/product-manual.md`](references/product-manual.md)
- 检索脚本：[`scripts/read_manual.py`](scripts/read_manual.py)
