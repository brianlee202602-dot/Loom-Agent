---
name: robot-bedroom-navigation
description: 向机器人网关发送导航去卧室的请求，并如实返回实际结果。当用户明确要求机器人去卧室、导航到卧室、前往 Bedroom，或提到卧室、bedroom、去卧室、导航到卧室时使用。不要用于状态查询，也不要用于除卧室外的其他目的地。
---

# 机器人卧室导航

使用此 skill 处理“让机器人去卧室”这一类明确导航请求。
执行时调用固定接口并发送固定负载，不要把它用于状态查询、路线规划解释或其他目的地。

## 适用场景示例

- 让机器人去卧室
- 帮我导航到卧室
- 让它前往 bedroom
- 让机器人现在去 Bedroom

## 关键词提示

- 卧室 / bedroom / Bedroom

## 脚本执行约定

- 调用 `execute_script` 执行导航脚本时，默认使用服务端统一配置的脚本超时时间。
- 不要主动传递 `timeout_seconds` 参数，也不要通过命令行参数额外传递 `--timeout`。
- 只有当用户明确要求使用特定超时时间时，才可以显式传递超时参数。
- 如果脚本最终返回超时或请求失败，需要如实说明，不要为了“更快返回”擅自缩短超时时间。

## 工作流

1. 先确认用户请求是“导航去卧室”，而不是查询位置、状态、电量或前往其他房间。
2. 需要确认接口约定时，读取 [`references/request-contract.md`](references/request-contract.md)。
3. 执行 [`scripts/post_bedroom_navigation.py`](scripts/post_bedroom_navigation.py) 发送固定 POST 请求；调用 `execute_script` 时不要显式传递 `timeout_seconds`，也不要额外追加 `--timeout`。
4. 如实返回接口结果；如果请求失败，不要虚构导航成功。
5. 如果用户要求去的不是卧室，明确说明此示例 skill 当前只处理卧室导航。

## 输出要求

- 回答使用中文。
- 成功时说明已发送卧室导航请求。
- 失败时说明失败原因、HTTP 状态或接口返回信息。

## 资源

- 接口说明：[`references/request-contract.md`](references/request-contract.md)
- 执行脚本：[`scripts/post_bedroom_navigation.py`](scripts/post_bedroom_navigation.py)
