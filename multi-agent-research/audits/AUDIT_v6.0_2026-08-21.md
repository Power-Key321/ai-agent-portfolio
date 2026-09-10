# adversarial-research v6.0 自审计求解赛 — 最终审计报告

**日期**: 2026-08-21 · **赛制**: 4队评定 → 交叉攻击(每案3票,≥2反驳淘汰) → 计分排行 → 综合结论综合
**约束宪法(等效制宪)**: E1 发现须有文件实据 / A1 仅审 SKILL.md+workflow.js / A2 致命=机制失效单点 / A3 排除风格偏好 / A4 ≥2/3反驳淘汰
**投票结果**: 48/48 confirmed · 0 refuted · 0 unclear · **17/17 案幸存（零淘汰）**

---

## 排行榜

计分规则：fatal high=20/med=12/low=6；opt high=10/med=6/low=3；被驳-4（本场无）；合并案件署名队各得满分（独立重复发现=信号增强）。

| 名次 | 队伍 | 得分 | 幸存/淘汰 | 代表作 |
|------|------|------|-----------|--------|
| 🥇 1 | T3 博弈操纵派 | **79** | 6/0 | S9 预算饿死攻击、S10 委员会无人看守、M2/M6 共同发现 |
| 🥈 2 | T0 架构审查派 | **76** | 6/0 | M2 综合结论垄断+守卫错对象、S1 空宪法颁布、M6 文档断裂 |
| 🥉 3 | T1 致命漏洞猎手 | **59** | 6/0 | M1 teamDefs缺id(共同)、S6 幸存判定、S5 违宪废票 |
| 4 | T2 工程实现派 | **55** | 6/0 | M1 teamDefs缺id(共同+人工实锤)、M3 预算透支、S7/S8 |

**灵感奖**: T2 工程实现派——M1 不仅发现 bug，还最先指出它与 `delegateDefs` 写法的对照差异（:551 vs :431），定位到根因模式。T1 攻击代表——3 条跨案增量（S1 触发面更宽、M2×S6 复合、M3+S9+S12 同根因链）。

---

## 致命漏洞（9 条，按修复优先级）

### P0 判定正确性（机制产出错误结果）

**M1. teamDefs 缺 id → 计分全面坍塌**（T1+T2，人工实锤 ✅）
- 位置：workflow.js:33-38 / :551 / :675-676 / :698
- `TEAM_DEFS` 无 `id` 字段，:551 构建 teamDefs 未补 id（对照 :431 delegateDefs 写法正确）→ `c.team.id === team.id` = `undefined === undefined` 恒真 → 全员同分、综合结论恒为 T0、winnerClaims 吞并全队。**v5.0 历史遗留**。
- 修：`:551` 改 `TEAM_IDS.map(id => ({ id, ...TEAM_DEFS[id] })).filter(t => t.name)`

**M2. 综合结论垄断 + 零幸存守卫判错对象**（T0+T3）
- 位置：workflow.js:698 / :717-736
- 合成只喂领先队 claims（与机制7"跨队融合"矛盾）；守卫 `winnerClaims.length===0` 应为 `confirmed.length===0`——负分计分下零 claim 队可夺冠并谎报"全军覆没"。
- ⚠️ **与 M1 耦合**：M1 的 bug 意外掩盖了 M2（winnerClaims 恒为全体）。**只修 M1 不修 M2 会引入垄断**。必须同修。
- 修：守卫改 `confirmed.length===0`；合成输入改全部 confirmed（标注队伍归属）。

**S6. 评委出错时多数反驳仍判幸存**（T2）
- 位置：workflow.js:650-652
- 5票/3阈值下 2 评委出错 → valid=3、2票refuted → `3>=3 && 2<3` → 幸存。1支持2反驳的 claim 进综合结论报告。与 prompt"不确定默认 refuted"方向相反。
- 修：`survives` 加多数约束 `(valid.length - refuted) > refuted`。

**S5. 违宪票是数学废票**（T1）
- 位置：VERDICT_SCHEMA + workflow.js:651
- `{refuted:false, unconstitutional:true}` 是 schema 合法输出但不计淘汰 → "为真但越界照样淘汰"被架空（有 prompt 层缓解，触发需模型偏离指令）。
- 修：计票改 `v.refuted || v.unconstitutional`（一行）。

**S9. 预算饿死操纵攻击**（T3）
- 位置：workflow.js:239 / :573-580 / :682-685
- 共享 fetchSlots 无按队配额 + relevance 自报 high 免预算 + 垃圾 URL 先占去重表 + 空 claims 永不扣分 = 零成本烧光对手预算的理性策略。
- 修：按队配额 `MAX_FETCH/teams.length`；high 不豁免；空 claim 来源计负分或占配额。

### P1 宪法机制完整性（v6.0 新增层的断裂）

**M4. 永恒条款文本匹配脆弱 + 落选静默蒸发**（T1+T0）
- workflow.js:475-479：逐字 text 匹配丢票 + 要求凑齐4票；落选者不进 minority_report 无日志。
- 修：eternityProposal 加 id（E1..En）按编号计票；落选写入 minority_report。

**S1. 空宪法颁布**（T0）
- workflow.js:460-529：表决全灭（agent 失败或条款两轮全未过）仍颁布 0 条款宪法，下游在空宪法上假性严格执行。
- 修：颁布前 `if (passed.length===0 && eternityPassed.length===0)` → 走降级路径。

**S3. 少数意见不进 Synthesis 上下文**（T1）
- constitutionBlock 只含通过条款，SYNTHESIS_PROMPT 却要求 caveats 引用少数意见 → 只能编造。
- 修：constitutionBlock 追加 minority_report 段。

**M6. 攻防一体/多轮修补迭代在代码中不存在**（T0+T3）
- SKILL.md 机制3/4/6 在 workflow.js 零控制流对应；自检清单恒假。**决策项**：实现多轮修补循环 OR 修改文档承认单轮。

---

## 优化点（8 条）

| ID | 案件 | 级别 | 修法要点 |
|----|------|------|---------|
| S2 | 宪法纯 prompt 注入，resource 条款与预算脱钩（**T3 注：这是宪法无牙的根基**） | high | 委员会 schema 加结构化 `limits{maxSources,maxClaims}` 覆盖 fetchSlots/MAX_VERIFY |
| S10 | 委员会无人看守（五权一次无监督调用，无 provenance/申诉） | high | COMMITTEE_SCHEMA 强制 sourceRefs；rejected 设 ≥2/4 申诉复活票 |
| S11 | "议程可挑战"纸面化（0a→0b 无挑战环节） | medium | 0a/0b 间加议程补充票 ≥2/4 强制加入 |
| S4 | votes/refuteRequired 无校验可配出必死局 | medium | 启动校验 `1<=refute<=votes`，clamp+log |
| M3 | 预算 high 豁免+透支为负（与 S9 同根因链） | medium | 统一 `fetchSlots<=0` 拦截或独立兜底额度 |
| M5 | normURL 丢 query 误杀 | low | key 加规范化 query |
| S7 | SYNTHESIS_PROMPT 打印 "Evidence: undefined" | low | 取最佳未反驳 verdict 的 evidence |
| S8 | 早退 stats 键名不一致+unconstitutionalKills 误计 | low | 复用 baseStats；违宪淘汰按阈值计 |
| S12 | F0 兜底 5 分刷分通道 | low | F0 权重 0（`?? 0`） |

---

## 跨案复合洞察（攻击代表贡献）

1. **病根**（T0 攻击代表）：判定逻辑依赖 prompt 软约束维持不变量，代码层没有硬 invariant——S5/S6/S9 都是这一模式。
2. **M2×S6 复合**（T1/T3）：S6 放水的幸存 claim 直接决定 M2 的综合结论归属，叠加后"事实相反的报告"概率显著上升；攻击者诱导评委超时（喂超长 claim）可同时放大两者。
3. **M3+S9+S12 同根因链**（T1）：relevance 自报 + high 豁免 + F0 默认分 = 完整预算操纵+刷分攻击面，应一并修。
4. **M3×M5 联动**（T3）：query 误杀省预算、high 放行透支预算——构造大量带 query 的 high 标 URL 可让 dedup 吞掉对手合法来源，低成本 DoS 式占位。
5. **M1↔M2 修复耦合**（本会话人工核验）：必须先修 M2 再修 M1（或同修），否则修复行为本身引入综合结论垄断。

## 下一步行动（优先级排序）

1. P0 四连修：M1+M2（同修）、S6、S5 —— 判定正确性
2. P1 宪法层：M4、S1、S3 —— 制宪机制完整性
3. P1 预算攻击面：S9+M3+S12 一并修
4. P2 治理层：S2（结构化 limits）、S10（委员会 provenance+申诉）、S11（议程挑战票）
5. P3 清扫：M5、S7、S8、S4
6. 决策项 M6：实现多轮修补循环 vs 文档对齐（需用户拍板）
7. 同步用户级旧副本：用户级 skill 目录下的同名技能仍是 v5.0（本场第 0 号发现：文档漂移）

## 竞赛元结论

- **零淘汰**：48 票全 confirmed——评定阶段"无实据=送分给对手"的倒扣激励有效过滤了空对空发现。
- **Agent 降级通道有效**：Workflow 引擎子代理当日持续 400，Agent 工具 fan-out 8/8 成功（4 评定 + 4 攻击）。
- **v6.0 制宪层本身经受住了审计**：表决数学（2/3/全票门槛）未被任何队伍攻破；问题集中在工程实现层和"宪法无代码之牙"。
