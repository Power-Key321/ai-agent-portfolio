# Multi-Agent Research Framework

把任何复杂任务转化为**前置制宪 + 约束内公开迭代**：先开**制宪会议**——议员团模拟人类立法流程博弈出**唯一约束宪法**（刚性锁死 + 日落失效）；然后每队**在宪法约束内**既是求解者也是评委，公开方案 / 攻击 / 评价，**跨队融合合成** + **多轮修补迭代** → 趋近**宇宙客观边界 + 内生宪法边界**双重约束下的最优解。

## 概述

**核心思想**：约束不是外部强加的红线，而是内生立法博弈的产出。先由议员团立法产生唯一约束宪法，再由多个研究队在宪法约束内攻防迭代，趋近双重边界（宇宙客观边界 + 内生宪法边界）下的最优解。唯一先验约束是宇宙客观边界：物理·数学·信息·计算。

**核心定位（v6.1 在 v6.0 基础上的硬化）**：

- ✅ **v6.0 继承：前置约束立法**（ConstitutionForge）——约束条件类比人类社会的法律，由模拟立法博弈内生产出
- ✅ **v6.0 继承：制宪权与求解权分离**（pouvoir constituant ≠ pouvoir constitué）：议员团独立于研究队
- ✅ **v6.0 继承：宪法刚性 + 日落条款**：颁布即锁死，本次博弈结束自动失效
- ✅ **v6.1 新增：跨队融合综合结论合成**——Synthesis 不再只取领先队，融合所有队伍幸存 claims（标注队伍归属），与机制 7"跨队融合"对齐
- ✅ **v6.1 新增：多轮修补循环**（M6 兑现）——对技能审计类研究任务，各队对已发现 fatal flaw 提 patch，3 票验证后采纳，≤3 轮迭代
- ✅ **v6.1 P0 修复（判定正确性）**：
  - M1: `teamDefs` 补 `id` 字段（v5.0 遗留 bug，修复后计分不再全员同分、领先队恒 T0）
  - M2: 综合结论合成改为跨队融合 + 守卫改 `confirmed.length===0`（防零 claim 队谎报"全军覆没"却胜出）
  - S5: 违宪票数学化——`v.refuted || v.unconstitutional`（为真但越界照样淘汰，从软约束变硬 invariant）
  - S6: 幸存判定加多数约束——`(valid.length - refuted) > refuted`（防评委出错时多数反驳仍幸存）
- ✅ **v6.2 P0+P1 修复（自审计研究回合第二轮新发现）**：
  - **S1**: 空宪法降级——议会团灭时 `constitution=null` + 日志告警，避免下游假性"严格"遵守空宪法
  - **S5c**: claim-level 硬 veto——任何评委标 `unconstitutional` 即整条 claim 淘汰（修复 v6.1 修复不彻底：vote-level OR 缺 claim-level hard veto）
  - **S9**: per-team `fetchSlots` 配额——去掉 global 池 + high-relevance 豁免，防止 1 队烧光预算
  - **M6-ctx**: `prevPatches` 累积——多轮修补时 Round 3 也能看到 Round 1 已采纳（原 `prevPatches = accepted` 只留最后一轮）
  - **M6-ver**: `PATCH_VERIFY_PROMPT` 签名加 `prevPatches` 参数，注入"已采纳修补"块供评委检查冲突/重复
- ✅ **v6.3 修复（自审计研究回合第三轮优先修补 + v6.1 旧 P1 收尾）**：
  - **M4**: 永恒条款 id 化——COMMITTEE_SCHEMA.eternityProposal + VOTE_SCHEMA.eternityVotes 改 `id` 字段（E1..En），落选写 `minority_report.eternity_failed`，修复 text 严格匹配静默蒸发（P0 升级）
  - **S3**: minority_report 进 constitutionBlock 拼接末尾（4 队共认的 P1）
  - **S7**: SYNTHESIS_PROMPT 改用 `c.verdicts.filter(!refuted).sort(confidence)[0].evidence` 替代字面 `c.evidence`（4 队共认的 P1）
- ❌ 抛弃人类**外部强加的**主观思维框架（法律/规则/习俗作为外来红线仍被拒绝）
- ✅ 唯一先验约束仍是**宇宙客观边界**：物理（能量守恒/熵增/光速/量子）· 数学（哥德尔/计算复杂性/信息论）· 信息（可获取性/香农熵）· 计算（图灵可计算/时空复杂度）
- ✅ **每队攻防一体**（公开方案 + 攻击 + 评价），公开透明，多轮修补迭代

**v6.0 的关键区分**：v5.0 拒绝的是**外部强加的**人类红线；v6.0 引入的是**内生博弈产出的**约束法——它不是"别人定的规矩"，而是"我们自己的制宪会议立法"。约束的合法性来自立法程序本身，不来自任何人类权威。

**核心机制速览**：

1. **前置制宪会议** → 约束由模拟立法博弈内生产出（议长议程 / 议员提案 / 委员会整合 / 2/3 表决 / 复议 / 颁布）
2. **宪法刚性 + 日落** → 博弈内锁死（约束可信），博弈后失效（不永久化）
3. **制宪权与求解权分离** → 议员团独立，防止为自己立法
4. **双重边界** → 宇宙客观边界（先验）× 约束宪法（内生）
5. **违宪审查硬约束** → v6.1 S5: 违宪票数学化，为真但越界的 claim 照样淘汰（不再靠 prompt 软约束）
6. **跨队融合综合结论合成** → v6.1 M2: Synthesis 输入改为全部 confirmed，标注队伍归属
7. **多轮修补循环** → v6.1 M6 兑现: 各队对致命漏洞提 patch，3 票验证，≤3 轮迭代
8. **判定正确性硬化** → v6.1 M1+S6: teamDefs 补 id，幸存判定加多数约束，计分不再坍塌

### 与 v5.0 / v6.0 / v6.1 的关键差异

| 维度 | v5.0 | v6.0 | **v6.1** |
|------|------|------|-----------|
| **约束来源** | 只有宇宙客观边界 | 宇宙边界 + 制宪会议内生立法 | 同 v6.0 |
| **范围控制** | 无 | 宪法 scope/exclusion 条款硬约束 | 同 v6.0 |
| **立法程序** | 无 | 议长议程→议员提案→委员会→2/3表决→复议→颁布 | 同 v6.0 |
| **宪法刚性** | 不适用 | locked + sunset | 同 v6.0 |
| **Verify** | 5 票对抗验证 | + 宪法法院票（软约束） | **违宪票数学化(S5) + 多数约束(S6) 硬 invariant** |
| **综合结论合成** | 领先队 claims | 领先队 claims（**M2 bug 垄断**） | **跨队融合全部 confirmed(标注队伍归属) + 守卫 `confirmed.length===0`** |
| **计分正确性** | OK | **M1 bug: teamDefs 缺 id → 全员同分、领先队恒 T0** | **M1 修复: teamDefs 补 id 字段** |
| **多轮修补** | 文档承诺（无实现） | 文档承诺（无实现） | **M6 兑现: PatchLoop 阶段(≤3 轮, 各队提 patch → 3 票验证)** |
| **失败防护** | 无 | 相关性/超多数/复议/刚性强制度 | + 违宪票硬约束 + 多数约束 + 跨队融合 |

### 调用方式

```
/multi-agent-research <复杂任务>
```

或工作流脚本：

```python
result = Workflow({
  "scriptPath": "./workflow.js",
  "args": {
    "task": "<复杂任务>",
    "config": {
      "constitution": True,   # v6.0 核心开关：前置制宪会议(默认开; false 退回 v5 无约束模式)
      "patchLoop": True,      # v6.1 新增：多轮修补循环(默认开; 技能审计类研究任务推荐; 普通研究类任务可关)
      "maxPatchRounds": 1,    # v6.1 新增：修补最大轮数(1-3, 默认1)
      "votes": 5,             # 每 claim 对抗验证评委数
      "refuteRequired": 3,    # 淘汰阈值(≥3/5 反驳)
      "maxFetch": 15,         # 抓取预算
      "maxVerify": 25,        # 验证 claim 上限
      "teams": ["T0","T1","T2","T3"],
    }
  }
})
```

### 适用场景

- **深度研究**：立法限定时间范围 / 来源等级 / 地域范围 / 终止条件，防止研究无底洞。
- **算法 / 产品设计**：立法限定平台边界 / 资源上限 / 兼容性要求，团队在约束内攻防。
- **任何容易"无限拓展"的开放任务**：命题越模糊，制宪价值越大。

---

## 设计哲学：8 大核心机制

### 机制 0（v6.0 核心新）：**前置制宪会议**（ConstitutionForge）
> 研究回合开始前，先立法。所有队伍在约束范围内攻防，避免无限制拓展。

**制度原型（深度调研 19 篇一手资料，2026-08-21）**：

| 子机制 | 人类制度原型 | 设计依据 |
|--------|-------------|---------|
| 议长议程设置 | 各国议会议程权 | 议程权=结果控制权 → 议长须中立且议程可被挑战 |
| 议员提案权 | 立法提案权（中国宪法64条：提案权专属） | 限制提案入口防议程操纵 |
| 委员会整合 | 1787 费城会议 Committee of Detail / 三读程序的委员会审查 | 把辩论成果整合为精确立法文本 |
| **相关性审查** | 美国众议院 germaneness / 希腊宪法74条 / 捷克宪法法院"野骑手"判例 | 与命题无关的条款（rider）直接退回，防夹带私货 |
| **逐条 2/3 超多数表决** | 美国 Article V / 德国 Art 79 / 日本 Art 96（全部 2/3） | 阿罗定理实证：~64% 超多数门槛在偏好分布良好时**防止孔多塞投票循环**；逐条单维表决防一揽子劫持 |
| **永恒条款全票通过** | 德国基本法 Ewigkeitsklausel（Art 1/20 永不可修） | 布坎南《同意的计算》：高外部成本决策须一致同意 |
| **1 轮复议** | 1787 制宪会议 reconsideration 规则（允许推翻已表决事项重新表决） | 僵局解法；参议院 cloture 思想：辩论必须有硬终结 |
| **刚性锁死** | Tsebelis 否决玩家理论 | 颁布后零中途否决者 = 约束可信；博弈中途禁止修宪 |
| **日落条款** | 罗马法"限时授权过期作废" / 现代 sunset provision | 宪法仅对本次博弈有效，下次任务重新制宪 |
| **违宪审查** | 宪法法院（奥地利1919/德国1949） | Verify 阶段新增"宪法法院票"：为真但越界的 claim 照样淘汰 |

**立法流程（6 步，约 10-15 agent 调用，占主流程开销 <10%）**：

```
0a 议长意图分析  → 产出议程(2-6个必须约束的议题)
0b 4 议员提案    → 每议员 1-4 条草案(立场: 聚焦/扩张/务实/质疑)
0c 委员会整合    → 合并重复 + 消解冲突 + 相关性审查(退回 rider) + 提炼永恒条款候选
0d 逐条表决      → 普通条款 ≥3/4 赞成(2/3超多数)；永恒条款 4/4 全票；每票附理由(协商民主)
0e 僵局复议      → 未过条款由委员会修正后重投 1 次(cloture: 仅此1轮)；再不过→少数意见记录
0f 颁布          → constitution.json: 刚性 locked + 日落 sunset + 条款 + 永恒条款 + 少数意见
```

**议员团构成（制宪权独立）**：

| 议员 | 代表利益 | 职责 |
|------|---------|------|
| **D0 聚焦派** | 收窄范围 | 防止范围蔓延，把模糊命题切成可回答边界 |
| **D1 扩张派** | 保留探索空间 | 攻击过度收窄，为非常规路径留通道 |
| **D2 务实派** | 资源/成本边界 | 限定来源数量/时间深度/工具范围 |
| **D3 质疑派** | 可证伪性 | 规定证据标准与终止条件 |

### 机制 1：**宇宙客观边界**（先验约束，不变）
> 没有不可触碰的边界，只有"宇宙是否允许"

| 边界类型 | 客观内容 | 主观内容（仍抛弃） |
|---------|---------|------------------|
| **物理边界** | 能量守恒 / 熵增 / 光速 / 量子不确定性 | 资源上限 / 单点依赖 / 技术选型 |
| **数学边界** | 哥德尔不完备 / 计算复杂性 / 信息论极限 | 行业经验 / 传统策略 |
| **信息边界** | 数据可获取性 / 香农熵 | 内幕信息 / 未来数据 |
| **计算边界** | 图灵可计算性 / 时间空间复杂度 | 算法选择 / 实现细节 |

### 机制 2：**目标导向 + 公开信息**（博弈空间）
- 核心目标：1 个清晰的复杂任务
- 信息全公开：方案 / 攻击 / 评价全部公开
- **v6.0 新增**：约束宪法全文公开，注入所有阶段提示词

### 机制 3：**攻防一体**（每队都是求解者 + 评委）
每队 3 角色：求解者（提交方案）/ 攻击者（≥1 个具体攻击）/ 评委（结构化评价）。
**v6.0 新增**：攻击与评价必须在宪法条款范围内——越界的攻击无效（违宪）。
**v6.1 兑现**：Verify 阶段的"宪法法院票"现为**数学硬约束**（S5: `v.refuted || v.unconstitutional` 计入 refuted）而非纯 prompt 软约束

### 机制 4：**多轮修补悖论迭代**（趋近最优）
- 每轮必须修补上一轮被攻击的漏洞
- 跨方法论迭代（禁止连续两轮相同方法论）
- 修补时引入的新破绽仍是有效 attack surface
- **v6.0 新增**：修补不得修宪——宪法刚性，任何"通过修改约束来修补"的尝试无效
- **v6.1 兑现 M6**：对技能/工作流审计类研究任务，新增 PatchLoop 阶段——各队对已发现 fatal flaw 提 patch，3 票验证后采纳，下一轮可提"修补的修补"。≤3 轮迭代（`CONFIG.maxPatchRounds`，默认 1）

### 机制 5：**双重边界评估**（v6.0 扩展）
- **先验边界**：物理可行性 / 数学可解性 / 信息可获取性 / 计算可行性（宇宙客观）
- **内生边界**：约束宪法条款（制宪会议立法产出）
- 评分表双轨制：4 项宇宙边界 × 合宪性检查

### 机制 6：**修补悖论的真实含义**
```
物理边界（光速）：永远不可突破
数学边界（哥德尔）：某些问题不可解
宪法边界（本次立法）：博弈内不可突破，博弈外(下次任务)可重新立法
修补 = 找到双重边界内的最优解
```

### 机制 7：**透明交付 + 灵感涌现**
- 透明交付：宪法全文 / 表决记录 / 方案 / 攻击 / 评价全部公开可查
- 少数意见（minority_report）随报告交付——未通过条款是下次制宪的线索
- 跨队融合 + 灵感奖

---

## 工作流：7 阶段（含制宪前置 + 修补循环）

### 阶段 0：**制宪会议**（v6.0 核心新，10-15 agents）

产出 `constitution.json`：

```json
{
  "version": 1,
  "rigidity": "locked — 颁布后本次博弈内不可修正",
  "sunset": "本次博弈结束即失效; 下次任务须重新制宪",
  "intentSummary": "议长对命题真实意图的提炼",
  "eternity_articles": [
    {"id": "E1", "text": "所有 claim 必须可证伪且带来源", "vote": "4-0"}
  ],
  "articles": [
    {"id": "A1", "type": "scope", "text": "检索范围限定为...", "vote": "3-1", "rationale": "..."},
    {"id": "A2", "type": "exclusion", "text": "排除...方向", "vote": "4-0"},
    {"id": "A3", "type": "resource", "text": "来源上限...", "vote": "3-1"},
    {"id": "A4", "type": "evidence", "text": "证据标准: 仅接受...", "vote": "3-1"},
    {"id": "A5", "type": "termination", "text": "当...时判定无解并停手", "vote": "3-1"}
  ],
  "minority_report": [{"id": "A6", "text": "...", "vote": "2-2", "note": "未达 2/3 门槛"}],
  "rejected_riders": [{"text": "...", "reason": "与命题无关(rider)"}],
  "quorum": {"articles": "≥3/4 (2/3 超多数)", "eternity": "4/4 (一致同意)"}
}
```

**降级保护**：议长/委员会/提案任一环节失败 → 自动降级为无宪法模式继续（不阻塞主流程）。

### 阶段 1：**ProblemForge 问题分解**（宪法约束内）
- 每个子问题必须完全处于 scope 条款内、不触碰 exclusion 条款
- rules 第一条固定为"不得违反约束宪法 A1-An"

### 阶段 2：**并行求解**（4 队并行，宪法约束内）
- 队：**T0 主攻手**（权威一手）/ **T1 逆势者**（反证）/ **T2 实务派**（落地）/ **T3 前沿哨**（最新边缘）
- 共享 URL 去重 + 抓取预算管控
- 提取 claims 时执行合宪性自检：越界 claim 直接丢弃

### 阶段 3：**Verify 对抗验证**（N 票 + 宪法法院票）
- 每条 claim 5 个评委专职反驳（≥3/5 淘汰）
- **v6.1 修复**：违宪票数学化——`v.refuted || v.unconstitutional` 计入 refuted（**S5**：为真但越界照样淘汰的硬约束）
- **v6.1 修复**：幸存判定加多数约束——`(valid.length - refuted) > refuted`（**S6**：防评委出错时多数反驳仍幸存）
- **v6.2 修复**：claim-level 硬 veto——`hasUnconstitutional = valid.some(v => v.unconstitutional)`，任意评委标违宪即 `survives=false` 且 `isRefuted=true`（**S5c**：修复 v6.1 S5 修复不彻底的 vote-level OR 漏洞）
- 第 0 项检查——违宪审查：超出 scope / 触碰 exclusion / 违反 evidence 标准 → refuted=true 且 unconstitutional=true
- 统计单独追踪 unconstitutionalKills

### 阶段 4：**Score 计分排行**
- 幸存：子问题分 × 重要性权重(3/2/1) × 置信权重(1/0.6/0.3)
- 被驳：倒扣 0.5×子问题分
- **v6.1 修复 M1**：`teamDefs` 补 `id` 字段，计分正确执行（v5.0 bug：全员同分、领先队恒 T0）

### 阶段 5：**Synthesis 综合结论合成**（v6.1 跨队融合）
- **v6.1 修复 M2**：输入改为全部 confirmed claims（标注队伍归属），不再只取领先队
- 报告开头声明所依据的宪法版本与条款范围
- 报告首部标注领先队（按排行榜分）但内容融合所有队伍幸存证据
- caveats 必须包含"约束宪法导致的覆盖缺口"（少数意见中可能有线索）

### 阶段 6：**PatchLoop 多轮修补**（v6.1 M6，可选）
- 仅当 `CONFIG.patchLoop !== false`（默认开）时启用
- **第 1 轮**：各队并行提 0-3 条 patch（针对已发现 fatal flaw）→ 3 票验证（≥2 approve 采纳）
- **第 2+ 轮**：基于上轮采纳 patch 提"修补的修补"或新发现 flaw
- ≤3 轮（`CONFIG.maxPatchRounds`，默认 1）
- **v6.2 修复 M6-ctx**：`prevPatches = [...prevPatches, ...accepted]`（累积所有已采纳的 patches，多轮修补时后续轮次能参考全部历史）
- **v6.2 修复 M6-ver**：`PATCH_VERIFY_PROMPT` 签名加 `prevPatches` 参数，注入"已采纳修补"块供评委检查新 patch 与已采纳的冲突/重复
- 适用场景：**技能/工作流审计类研究任务**（如本框架的自我审计），不适用普通研究类任务
- 输出：`patchResult` 字段，含 rounds/totalAccepted/acceptedPatches（每条带 flawId/title/team/diff/approveVotes）

---

## 评分维度（双轨制，v6.0）

### 宇宙边界轨（不变，各 25%）

| 维度 | 评估方法 |
|------|---------|
| 物理可行性 | 能量守恒 / 熵增 / 光速 / 量子不确定性 |
| 数学可解性 | 方程是否有解 / 计算复杂度 / 信息论极限 |
| 信息可获取性 | 数据是否公开可获取 / Shannon 熵 |
| 计算可行性 | 图灵可计算性 / 时空复杂度 |

### 宪法合宪轨（v6.0 新增，一票否决）

| 检查 | 执行点 |
|------|--------|
| scope 条款符合 | ProblemForge 问题分解时 / Verify 宪法法院票 |
| exclusion 条款回避 | 并行求解搜索自检 / Verify 宪法法院票 |
| evidence 标准达标 | Fetch 来源评级降级 / Verify 宪法法院票 |
| resource 上限遵守 | 抓取预算管控 |

---

## 失败模式与防护（立法博弈经典失败 → 本框架的对应防护）

| 人类立法失败模式 | 历史案例 | 本框架防护 |
|----------------|---------|-----------|
| **循环多数**（孔多塞 A>B>C>A） | 社会选择理论 | 逐条单维表决 + 2/3 超多数（~64% 防循环） |
| **修正案劫持 / 圣诞树法案** | 美国 rider / 2010 学生贷款绑医保案 | 委员会相关性审查（退回无关条款） |
| **一揽子劫持** | omnibus bill | 逐条表决，禁止捆绑 |
| **多数暴政** | 麦迪逊《联邦党人》第10篇 | 超多数门槛 + 永恒条款一致同意 |
| **僵局** | 邦联条例一致同意瘫痪 | 1 轮 reconsideration 复议 + 少数意见记录（不阻塞） |
| **议程操纵** | 议程设置权研究 | 议长议程公开 + 议员可挑战 + 提案立场多元化 |
| **约束漂移** | 魏玛宪法 2/3 多数任意修宪 → 1933 授权法 | 刚性 locked：博弈内禁止修宪 |
| **约束永久化** | 日本宪法 78 年零修正（过度刚性） | 日落条款：博弈结束自动失效 |

---

## 自检清单（v6.0）

### 制宪会议（必检）
- [ ] 议长议程是否覆盖命题真正需要约束的维度？
- [ ] 4 议员是否按各自立场实质提案（而非同质化）？
- [ ] 委员会是否执行了相关性审查（rider 退回）？
- [ ] 表决是否逐条进行、每票附理由？
- [ ] 普通条款 ≥3/4、永恒条款 4/4 门槛是否严格执行？
- [ ] 复议是否只有 1 轮（cloture 硬终结）？
- [ ] constitution.json 是否含 rigidity=locked + sunset？

### 宪法执行（必检）
- [ ] ProblemForge 子问题是否全部合宪？
- [ ] 并行求解搜索/提取是否做合宪自检？
- [ ] Verify 是否执行违宪审查（宪法法院票）？
- [ ] 综合结论报告是否声明宪法版本？

### 攻防一体 / 迭代 / 透明（沿用 v5）
- [ ] 每队 3 角色？攻击基于边界论证？
- [ ] 修补上一轮漏洞？跨方法论？
- [ ] 所有方案/攻击/评价/表决记录公开？

---

## 风险提示（v6.0）

- **制宪质量决定博弈质量**：约束法过死会漏掉正解（D1 扩张派的作用就是对抗这一点）；过松则失去意义（D0 聚焦派对抗这一点）。2/3 超多数强制两派妥协。
- **少数意见是资产**：未通过条款记录了"立法博弈中被否决的方向"，综合结论的 caveats 应引用它们作为覆盖缺口提示。
- **日落≠遗忘**：本次博弈的宪法可作为下次同类任务的立法参考（判例法思想），但不能直接复用——必须重新表决。
- **宇宙边界仍是终审**：宪法条款若与物理/数学边界冲突（如立法要求"突破香农极限"），宇宙边界优先——宪法法院应判该条款本身违"宇宙法"。

---

## 版本演进日志

### v6.0 → v6.1 升级日志

- **2026-08-21 v6.1**：自审计研究回合后修复 4 条致命缺陷 + 兑现 1 条文档承诺
  - M1 修复: `workflow.js:622` `teamDefs = TEAM_IDS.map(id => ({id, ...TEAM_DEFS[id]})).filter(t => t.name)`（v5.0 遗留 → 计分全员同分）
  - M2 修复: `workflow.js:771` 跨队融合 `winnerClaims = [...confirmed].sort(...)` + `workflow.js:791` 守卫改 `if (confirmed.length === 0)`
  - S5 修复: `workflow.js:720` 违宪票数学化 `v.refuted || v.unconstitutional`
  - S6 修复: `workflow.js:723` 多数约束 `(valid.length - refuted) > refuted`
  - S8 修复: `workflow.js:785` `unconstitutionalKills` 按阈值计（纯粹由违宪票杀死）
  - M6 兑现: 新增 `PATCH_SCHEMA`/`PATCH_VERIFY_SCHEMA`/`PATCH_PROMPT`/`PATCH_VERIFY_PROMPT`/Phase 6 PatchLoop 阶段（≤3 轮多轮修补）
  - Synthesis 签名变更: `SYNTHESIS_PROMPT(manifest, allConfirmed, leaderboard, constitutionBlock)` — 移除 `winner` 参数（跨队融合）
  - 元数据更新: `meta.description` + `meta.phases` 7 阶段（新增 PatchLoop）
  - 行号自检: v6.1 升级日志行号已与实际代码同步（2026-08-22 v6.1.1 修正 T2-F6）

### v6.1 → v6.2 升级日志

- **2026-08-22 v6.2**：自审计研究回合第二轮后修复 3 条 P0 致命 + 2 条共识 P1（24 行新代码）
  - **P0 S1 空宪法降级**: `workflow.js:579` 前加 `if (passed.length === 0 && eternityPassed.length === 0) { constitution = null; constitutionBlock = ""; log(...) }` 守卫（议会团灭不颁布 0 条款宪法，下游降级为无约束模式）
  - **P0 S5c claim-level 硬 veto**: `workflow.js:720-724` 加 `const hasUnconstitutional = valid.some(v => v.unconstitutional)`，`survives = !hasUnconstitutional && ...`，`isRefuted = hasUnconstitutional || refuted >= REFUTATIONS_REQUIRED`（修复 v6.1 vote-level OR 漏洞）
  - **P0 S9 per-team fetchSlots**: `workflow.js:266` 改 `fetchSlotsByTeam = new Map(TEAM_IDS.map(id => [id, Math.floor(MAX_FETCH / max(TEAM_IDS.length, 1))]))` + `workflow.js:644-650` 取 `teamSlots = fetchSlotsByTeam.get(searchResult.team.id)` 替代 global 池
  - **P0 M6-ctx prevPatches 累积**: `workflow.js:880` 改 `prevPatches = [...prevPatches, ...accepted]`（多轮修补时 Round 3 也能参考 Round 1 已采纳）
  - **P1 M6-ver PATCH_VERIFY 传参**: `workflow.js:463` `PATCH_VERIFY_PROMPT(patch, v, task, prevPatches)` 签名加 prevPatches + prompt 注入"已采纳修补"块 + `workflow.js:864` call site 传参
- 总计 6 patches / 24 行新代码，syntax OK 验证通过 (935 lines)
- 审计报告: `.agents/skills/multi-agent-research/AUDIT_v6.1_2026-08-22.md`

### v6.2 → v6.3 升级日志

- **2026-08-22 v6.3**：自审计研究回合第三轮后优先修补 v6.1 旧 P0/P1 + v6.2 文档元数据（7 patches / 14 行新代码）
  - **P0 M4 永恒条款 id 化**: `COMMITTEE_SCHEMA.eternityProposal` 加 `id` 字段（`{ id, text, rationale }`），`VOTE_SCHEMA.eternityVotes` 改 `{ id, approve, reason }`（移除 text），`workflow.js:548-557` 改为 `find(v => v.id === eId)` id 匹配 + 跟踪 `eternityFailed`，`workflow.js:597` 把 `eternityFailed` 写入 `minority_report`（type: "eternity"），修复委员会微调措辞导致 4 票静默蒸发的根因 bug
  - **P1 S3 minority_report 进 constitutionBlock**: `workflow.js:608` 拼接末尾追加 `### 少数意见(2-2 条款 + 永恒条款落选, 下次制宪参考)` 段，让 Synthesis 阶段 agent 拿得到真实少数意见数据（不再编造）
  - **P1 S7 Synthesis Evidence fix**: `workflow.js:421` 改用 `c.verdicts.filter(v => !v.refuted).sort(confidence)[0]?.evidence || c.quote` 替代字面 `c.evidence` 引用（EXTRACT_SCHEMA 无 evidence 字段导致 100% 触发字面 "undefined"）
  - **P3 文档元数据**: `FRAMEWORK.md` 标题 v6.1 → v6.3，`FRAMEWORK.md` version 字段 6.2.0 → 6.3.0
- 总计 4 patches / ~14 行新代码，syntax OK 验证通过 (941 lines)
- 审计报告: `.agents/skills/multi-agent-research/AUDIT_v6.2_2026-08-22.md`
- **v6.3 未修 v6.2 新发现**（待 v6.4 评估）：M6-ver.1 PATCH_SCHEMA.maxLength (P0) + N1 S9 0预算 (P0) + N2 unconstitutionalKills指标stale (P1) + S5c.1 单评委独裁 (P1) + S5c.4 错误穿透 (P1) + S9.2 dupes不扣slot (P1) + M2-cmp F0刷分 (P1) + NEW-2 PatchLoop去重 (P2) + 行号 92% 漂移（系统性问题，建议添加 lint workflow）

### v6.3 → v6.4 升级日志

- **2026-08-22 v6.4**：自审计研究回合第四轮后应用 4 P0 + 6 P1 + 9 v6.2 遗留 + 元数据完整化 = **~16 patches / ~30 行新代码**
  - **P0 NEW-7 VOTE_PROMPT 同步 e.id 标签**: `workflow.js:336` 改 `**" + (e.id || "E" + (i+1)) + "**` 替代 array position 索引；同步修改 VOTE_PROMPT 文字提示"id 字段填 E 编号原样,不要填 text"
  - **P0 NEW-8 ballot 端 id fallback**: `workflow.js:551` `find(v => (v.id || "E" + (bIdx+1)) === eId)` — 防止 LLM 偏离 schema 漏填 id 时 0 票静默
  - **P0 META-1 workflow.js 文档元数据完整化**: `workflow.js:3` description 累加 v6.2/v6.3/v6.4 修复清单；`workflow.js:16-19` 头部注释 + 修复清单 v6.1 → v6.4 完整累加
  - **P0 META-2 FRAMEWORK.md frontmatter description**: `FRAMEWORK.md` v6.2 → v6.4 完整累加所有版本修复
  - **P1 M6-ver.1 PATCH_SCHEMA.title maxLength**: `workflow.js:213` `maxLength: 200` 防 8KB title DoS（Round 2 1 队提 8KB → Round 3 评委 prompt 截断）
  - **P1 N2 unconstitutionalKills 指标修复**: `workflow.js:806` `> 0` 替代 `>= REFUTATIONS_REQUIRED`，避免 1-2 票违宪 kills 漏统
  - **P1 S7 c.quote 兜底**: `workflow.js:421` `... || c.quote || "(无证据)"` 防空字符串
  - **P1 S3 minority_report 截断**: `workflow.js:600` `text: (f.text || "").slice(0, 500)` 防 50KB text 注入
  - **P1 S4 CONFIG clamp**: `workflow.js:25-28` votes 1-10, refuteRequired 1-votes, maxFetch 1-100, maxVerify 1-200 — 防 votes=1000 OOM, maxFetch=0 砖化
  - **P1 N1 S9 余数分配**: `workflow.js:267` `baseSlots + (idx < remainder ? 1 : 0)` 替代 floor — 保证 sum=MAX_FETCH,无 0 slots 砖化
  - **P1 S5c.1 quorum 守卫**: `workflow.js:744` `unconstitutional >= ceil(VOTES/2)` 替代 `valid.some(v=>v.unconstitutional)` — 防 1 票独裁
  - **P1 S5c.4 errored 半数穿透**: `workflow.js:744` `errored > VOTES/2` → isRefuted=true — 防限流时 4/5 评委 errored 永挂 limbo
  - **P1 S9.2 dupes 扣 slot**: `workflow.js:657-660` dedup 路径也扣 slot — 防 1 队刷 dupes 占满其他队实际预算
  - **P1 S1×S5c cascade 联动**: `VERIFY_PROMPT` 401 注入"无宪法模式,unconstitutional 字段请保持 false" 替代违宪审查提示 — 防 constitution=null 后 S5c 误杀
  - **P1 M2-cmp F0 过滤**: `workflow.js:772-778` surv+rej 都加 `if (!c.subProblemId || c.subProblemId === "F0" || !problemPoints[c.subProblemId]) continue` — 防专攻 F0 模糊边缘 claim 刷分
  - **P1 NEW-2 PatchLoop 轮内去重**: `workflow.js:874-883` `seenPatches` Set by `flawId+title` — 防 4 队协调刷量占用修复位置
- 总计 15 patches / ~30 行新代码, syntax OK 验证通过 (~970 lines)
- 审计报告: `.agents/skills/multi-agent-research/AUDIT_v6.3_2026-08-22.md` (4 队 34 finding, 4 P0 + 6 P1 + 5 P2)
- **v6.4 仍 open finding (待 v6.5 评估)**: S3 minority_report id 未转义 (P2 cosmetic) + CONF_RANK 抽常量 (P2) + S7 SORT-NaN 守卫 (P2) + 文档行号 100% 漂移（系统性问题，已接受 P2）

### v6.4 → v6.5 升级日志

- **2026-08-22 v6.5**：自审计研究回合第五轮后应用 2 P0 + 3 P1 + 4 P2 = **9 patches / ~20 行新代码**
  - **P0 CASCADE-1 VERIFY_PROMPT 三分支重构**: `workflow.js:411` 重构为三路 (constitution && constitutionBlock → 违宪审查; constitution===null → 无宪法降级 + 提示 unconstitutional=false; 默认 → 基础审查) — 解决 v6.4 cascade unreachable dead code（v6.2 S1 强制 constitutionBlock="",v6.4 cascade 注永不显示）
  - **P0 N1-EDGE S9 每队 ≥ 1 slot**: `workflow.js:271` `Math.max(1, ...)` 替代 `Math.floor(...)` — 解决 16 队+15 fetch 时 1 队仍 0 slot 单队砖化
  - **P1 M6-ver.1 全字段 maxLength**: `workflow.js:212-218` title:200 / description:2000 / diff:2000 / targetFile:200 / targetLines:100 / riskNote:1000 / flawId:50 — 防 8KB description 注入 DoS
  - **P1 NEW-8 索引语义**: `workflow.js:558` fallback `E" + (eIdx + 1)` 替代 `E" + (bIdx + 1)` — 4 议员全偏离 schema 时 fallback 散落到 4 个不同 eternity 修复
  - **P1 CONFIG 0 吞掉**: `workflow.js:25-28` `?? default` 替代 `|| default` + `Math.floor(Number(...))` 浮点规范化 — 用户显式 votes:0 不再被默认值吞
  - **P2 CONF_RANK 抽常量**: `workflow.js:267-269` 抽 `const CONF_RANK = {high:3, medium:2, low:1}` — 消除 3 处重复 magic number
  - **P2 bestVerdict() helper**: `workflow.js:270-273` 抽 `const bestVerdict = c => c.verdicts.filter(v => !v.refuted).sort((a, b) => (CONF_RANK[b.confidence] || 0) - (CONF_RANK[a.confidence] || 0))[0]` — 消除 2 处重复 sort
  - **P2 Synthesis claim 截断**: `workflow.js:424` `(c.claim || "").slice(0, 500)` 防 50KB claim 溢出综合结论 prompt
- 总计 8 patches / ~20 行新代码, syntax OK 验证通过 (975 lines)
- 审计报告: `.agents/skills/multi-agent-research/AUDIT_v6.4_2026-08-22.md` (T0+T1/T2+T3 联合审计, 11 finding 含 2 P0)
- **v6.5 仍 open finding (接受 P2-P3)**: S3 minority_report id 未转义 (P2) + 文档行号 100% 漂移（系统性问题，已接受）

制度依据全部来自 2026-08-21 对 19 篇一手资料的深度调研：美国1787制宪会议 / Article V / 德国基本法79条+永恒条款 / 日本宪法96条 / 中国宪法64条 / 芬兰修宪程序 / 威斯敏斯特三读 / germaneness 规则 / cloture / 阿罗不可能定理 / 孔多塞悖论 / 布坎南《同意的计算》/ Tsebelis 否决玩家 / 协商民主 Fishkin 五特征 / 日落条款 / 宪法法院史。

### v6.5 → v6.6 升级日志

- **2026-08-22 v6.6**：回应用户对"研究必须落到可执行验证、不能停在理论"的硬性要求。**核心升级 = 把"实际执行"从 prompt 软约束升级为 E4 永恒条款 + ARTIFACT_SCHEMA 必填 + Verify 阶段独立重跑硬约束的三角硬架构**。共 7 处改动 / +59 行新代码 (975 → 1034 lines, syntax OK)：

  - **P0 E4 永恒硬约束**: `COMMITTEE_PROMPT` 加第 5 步强制要求：若任务可能涉及策略/算法/代码/可执行验证，委员会必须提议 E4 永恒条款（"任何策略/算法/可执行类 claim 必须附 (i) 脚本路径+SHA256 (ii) 真实实跑 stdout (iii) 落盘数据+SHA256 (iv) falsification (v) reproduceCommand, 缺一即 refuted, 评委必须独立重跑验证"）。不适用则显式说明"纯文献研究不需要 E4"。
  - **P0 EXTRACT_SCHEMA.claims[].artifact**: 新增必填字段 `scriptPath`(maxLength 500) / `sha256`(64字符严格) / `stdout`(<8KB) / `dataPath` / `dataSha256`(可选) / `falsification`(maxLength 500) / `reproduceCommand`(maxLength 500)。策略/算法类 claim 在 Fetch 阶段必须填此对象。
  - **P0 ENFORCE_ARTIFACT 配置开关**: `CONFIG.enforceArtifact` 默认 true(可显式 false 关闭,仅 research 类型有意义)。为所有后续阶段 (Fetch/Verify/Synthesis) 提供单一真相源。
  - **P0 FETCH_PROMPT 加 E4 提示**: 任务类型 taskType ∈ {code, market, hybrid} 时, FETCH 阶段会注入明确的"必须实际 Write/Edit 脚本 + Bash 实跑 + 落盘数据 + 算 SHA256"指令, 缺 artifact = Verify 阶段被 E4 单独否决。
  - **P0 VERIFY_PROMPT 加 Check 0.5**: 评委拿到 claim 后, 看到 artifact 必须**真正独立重跑** `reproduceCommand`, 校验 4 项: (a) SHA256 匹配 (b) stdout 一致 (c) dataPath 存在+dataSha256 匹配 (d) falsification 是否被违反。任一项不通过即 refuted=true。若无法独立重跑(Bash 不通/超时/沙箱拒绝)直接 refuted=true, evidence='E4-verifier-unable-to-reproduce'。**不允许口头声明, 不可信纯文字策略类 claim**。
  - **P0 VERIFY artifact 字段显示**: 待验证 claim 区会展开 claim.artifact 全部字段, 评委可直接对照 (scriptPath/sha256/stdout/dataPath/falsification/reproduceCommand), 不可缺。
  - **P0 refuted 规则追加 E4 触发条件**: 原 refuted 5 条 (不被支持/被矛盾/来源不匹配/过时/营销废话) + 违宪 → 新增第 7 条 "E4 artifact 缺失或独立重跑失败"。

  **v6.6 关键意义**：
  1. 终结了"PatchLoop 只提 diff 不应用"的理论/实践脱节死锁（Round 3 某实跑类任务 6 patches 提议 0 应用）
  2. 终结了"研究类任务产出 0 行可执行代码"的纯理论倾向（每条策略类 claim 必须配可重跑脚本）
  3. 把"评委必须独立验证"从 prompt 软约束升级为"无法独立验证 = refuted"硬约束
  4. 为下一步 Round 4 某实跑类任务奠定基础：4 队必须真实写脚本 + 真实实跑 + 真实落盘，缺一即被 E4 否决

  **v6.6 未修 (接受 P2-P3)**：S3 minority_report id 未转义 (P2) + 文档行号漂移（系统性问题，已接受）+ E4 误判边界（执行 verifier agent 自己的 Bash 不通时一律 refuted, 可能误杀强 claim, 待 v6.7 评估 edge case）

  **调用方式不变**：`Workflow({scriptPath: "./workflow.js", args: {task: "...", config: {constitution: true, patchLoop: true, maxPatchRounds: 1, votes: 5, maxFetch: 15, maxVerify: 25}}})`。

  **新增 config 选项**：`enforceArtifact: false` 可关闭 E4（仅对纯文献 research 任务有意义）。

### v6.6 → v6.7 升级日志

- **2026-08-24 v6.7**：回应用户"重新审查制宪会议是否**增强约束**而非**降低效率**"的审计结论。Round 5 实测暴露**决策效率退化**：E1 永恒条款要求诚实自标"THEORETICAL_UNVERIFIED"，使 claim 在博弈内**不可证伪** → 40 评委仅 4 反驳票(10%)、8/8 策略全幸存、Verify 消耗 87% agent 配额 0 淘汰。**核心升级 = 三轨裁决 + 五视角评委 + 游戏内可判定性，把"诚实"从幸存豁免变为分轨路径**。共 8 处改动 / +67 行新代码 (1034 → 1101 lines, ESM import 验证 syntax OK)：

  - **P0 VERDICT_SCHEMA + 三轨裁决**: VERDICT_SCHEMA 新增必填 `track` 枚举 `{DEPLOYABLE, PROBE, REJECTED}`。**DEPLOYABLE** = claim 证据在本场博弈内已闭合(被引文支持+来源匹配+E4 重跑通过+合宪+视角无实质反驳)；**PROBE** = 核心断言依赖博弈内**不存在的证据**(未来运行数据/未发生事件/博弈外实验)；**REJECTED** = 有反证/来源不足/过时/营销/违宪/E4 缺失。`refuted = (track === "REJECTED")`。修复 Round 5 "诚实护城河"(40 评委 0 淘汰)。
  - **P0 JUDGE_LENSES 五视角评委**: 新增 `JUDGE_LENSES` 数组(数据完整性/逻辑数学/证据可达性/合宪性/对抗逆向选择)，`VERIFY_PROMPT(claim, v, ...)` 改为块函数按 `v % 5` 分配专属视角，开头声明视角、结尾按视角深挖。修复 Round 5 克隆评委问题(5 个相同 prompt → 投票高度相关 → 每策略最多 1 张异见票)。
  - **P0 PROBE 轨落地**: Verify 阶段 `trackVotes` 统计三轨，`isDeployable = DEPLOYABLE > valid.length/2`(严格多数)，`isProbe` = 未淘汰且未达多数。拆分输出 `confirmed`(DEPLOYABLE) / `probes`(PROBE) / `killed` / `unverified`。**诚实标注"理论值/未验证"不再让 claim 自动幸存——只是进 PROBE 轨而非 REJECTED 轨**。
  - **P0 decidableTest(游戏内可判定性)**: `COMMITTEE_SCHEMA` 每条保留条款必填 `decidableTest`，宪法颁布/渲染同步映射。裁决者用博弈进行期间可获得的证据即可判定。**禁止把判定标准锚定在博弈结束后才存在的证据上**(如"上线后的真实运行记录")。立法教训(Round 5 实证)：证据门槛不可达 = 验证阶段空转。
  - **P1 Synthesis 三输入**: `SYNTHESIS_PROMPT` 签名扩展 `(manifest, allConfirmed, leaderboard, constitutionBlock, probes, killed)`，注入 `probeBlock`(PROBE 清单: 需未来数据验证的线索) + `dissentBlock`(REJECTED 异见证据的正面吸收)。SYNTHESIS_SCHEMA 新增 `probeList`。**最终结论只能使用 DEPLOYABLE claims**，PROBE 列入 caveats/下一步验证方向。
  - **P1 汇总兜底**: `confirmed.length===0` 时综合结论分支同样注入 probes，保证"全部 PROBE"时也有合成产物而非空报告。
  - **P0 meta 同步**: `meta.description` 追加 v6.7 三轨裁决说明，`meta.phases` Verify detail 更新为"每条 claim N 票三轨对抗验证(DEPLOYABLE/PROBE/REJECTED; 五视角评委; 违宪票+E4重跑否决; DEPLOYABLE须严格多数)"。

  **v6.7 关键意义**：
  1. 修复"诚实护城河"导致的**验证阶段空转**——真实性维度增强(DEPLOYABLE 门槛更高)且决策效率恢复(三轨分流，不再二元幸存)
  2. 修复**克隆评委投票相关**——五视角强制差异化，异见票从"最多1张"恢复到独立
  3. 把**"证据可达"从软约束升级为宪法条款硬约束**——decidableTest 让宪法条款自身可判定
  4. Round 5 使用 1-agent 压缩制宪(非真实 6 步流程)——真实流程的约束增强性在此前轮次已 5 轮自审计验证

  **v6.7 未修 (接受 P2-P3)**：S3 minority_report id 未转义 (P2) + 文档行号漂移（系统性问题，已接受）+ E4 误判边界（v6.6 遗留，待评估）

  **调用方式不变**：`Workflow({scriptPath: "./workflow.js", args: {task: "...", config: {constitution: true, patchLoop: true, maxPatchRounds: 1, votes: 5, maxFetch: 15, maxVerify: 25}}})`。

### v6.7 → v6.8 升级日志

- **2026-08-24 v6.8**：v6.7 修复裁决逻辑后，审计残留聚焦**执行层**——4 条 🔴 高（Verify 评委 effort=low 对抗不足 / E4 无法重跑一律 refuted 误杀真 claim / agent 无重试 429 静默丢票 / 全局配额无熔断）。**核心升级 = 把"执行韧性"从无保障变为硬保障**。共 6 处改动 / +33 行新代码 (1101 → 1134 lines, ESM import 验证 syntax OK, 14/14 单元测试通过)：

  - **P0 Verify 评委 effort low→medium**: `workflow.js:870` `effort: "medium"`（Round 5 40 评委 0 淘汰部分源于 effort=low；三轨机制修复逻辑漏洞，medium 修复对抗深度）
  - **P0 E4 重跑失败三态分级**: `workflow.js:497-503` Check 0.5 重构为三态——(i) 重跑成功+(b)(d) 通过 → 可支撑 DEPLOYABLE；(ii) 重跑成功但结果不符/falsification 违反 → 硬证伪 REJECTED (E4-self-check-failed)；(iii) SHA256 不符/dataPath 缺失/无法独立重跑(环境) → **PROBE (E4-unverifiable)，不据此淘汰**。修复 v6.6 自标注的"verifier Bash 不通一律 refuted 误杀真 claim"edge case。缺 artifact 的 claim 也改走 PROBE 而非 REJECTED。
  - **P0 agent 退避重试**: 新增 `sleep`(setTimeout 带降级) + `retryAgent`(尝试时检查预算 → 空结果指数退避 4s/8s 重试 ×2) 包装**全部 11 个 agent 调用点**(speaker/delegates/committee/votes/amend/problemforge/search/fetch/verify/synthesis/patch/patchVerify)。修复 Round 5 41/46 agent 因 API 429 失败被 filter(Boolean) 静默丢弃。
  - **P0 totalAgentBudget 全局配额熔断**: `CONFIG.totalAgentBudget`(默认 250, 10-2000) + `agentsUsed` 计数器 + `retryAgent` 内熔断守卫 + **Verify 前动态计算 `votableClaims`**（预留 synthesis 预算 `1+TEAMS×rounds×4` 后按 `floor(剩余/VOTES)` 截断）。修复 claims×VOTES 冲爆全局配额（maxVerify 原为唯一闸门）。
  - **P1 E4 artifact 缺失降权排序**: `workflow.js:836` `artifactRank` 使 ENFORCE_ARTIFACT 下无 artifact 的 claim 排最后——Verify 预算优先给有 artifact 的，缺 artifact 不再占用验证配额。
  - **P1 MAX_PATCH_ROUNDS 上移**: 顶部统一声明，供预算预留复用（删除 PatchLoop 内重复声明）。
  - **meta 同步**: description 累加 v6.8 修复清单 + Verify phase detail 更新。

  **v6.8 关键意义**：
  1. 终结"429 限流 → 静默丢票 → 结果残缺"（Round 5 41/46 失败不再发生）
  2. 终结"环境无法重跑 → 误杀真 claim"——E4 从二元(过/杀)变三态(过/杀/待验证)
  3. 终结"Verify 冲爆全局配额挤掉 Synthesis/PatchLoop"——熔断 + 预算预留双层防护
  4. 对抗深度提升（effort medium）针对 Round 5 "40 评委 0 淘汰"的残留弱项

  **v6.8 未修 (接受 P2-P3)**：S3 minority_report id 未转义 (P2) + 文档行号漂移（系统性问题，已接受）+ Score 阶段对产出影响低（P2 设计冗余，leaderboard 已注入综合结论上下文，0 agent 成本，暂不改）。

  **新增 config 选项**：`totalAgentBudget: 250`（全局 agent 数熔断上限）。

  **调用方式不变**：`Workflow({scriptPath: "./workflow.js", args: {task: "...", config: {constitution: true, patchLoop: true, maxPatchRounds: 1, votes: 5, maxFetch: 15, maxVerify: 25, totalAgentBudget: 250}}})`。
