# adversarial-research v6.1 自审计求解赛 — 第二轮最终报告

**日期**: 2026-08-22 · **赛制**: 4队 Assess → CrossAttack (4攻击agent × 13 finding) → 1 淘汰 / 12 幸存 → PatchLoop 4队提议 11 patches
**v6.1 起点**: P0 修复 M1+M2+S5+S6+S8 + M6 多轮修补循环兑现
**投票结果**: CrossAttack 48/48 verdicts / M6-zc 被 T2+T3 联合反驳淘汰 / 其他 12 finding 全部幸存 / PatchLoop 11 patches 4队提

---

## 排行榜（按 finding 数量 × severity × ownership 数加权）

| 名次 | 队伍 | Assess 数 | Owner 案 | 代表作 |
|------|------|----------|---------|--------|
| 🥇 1 | T3 博弈操纵派 | 6 | 4 (S5c/M6-zc/M2-cmp/S9-co) | 攻击核武器级 S9 + 复合 M2-cmp + M6-zc 提报 |
| 🥈 2 | T1 致命漏洞猎手 | 6 | 3 (M6-ctx/M6-ver/S9-co) | M6 实施双 bug 提报 + S5 票数例证伪 |
| 🥉 3 | T0 架构审查派 | 5 | 2 (S7/S3) | 回归测试全 PASS + SKILL.md 行号漂移 |
| 4 | T2 工程实现派 | 6 | 3 (PL-def/PL-snp/S4-co) | 文档/配置漂移（已当场修一行号） |

**灵感奖**: T1 致命漏洞猎手 — M6 双 bug 自查（owner 自纠 + 主动暴露 M6-ver 评委盲问）

---

## v6.1 修复回归测试（T0 负责，结果全 PASS ✅）

| 修复 | 位置 | 状态 |
|------|------|------|
| M1 teamDefs 补 id | workflow.js:622 | ✅ 一致 |
| M2 winnerClaims 跨队融合 | workflow.js:771 | ✅ 一致 |
| M2 守卫 confirmed.length===0 | workflow.js:791 | ✅ 一致 |
| S5 违宪票 OR 入 refuted | workflow.js:720 | ✅ 一致 |
| S6 多数约束 | workflow.js:723 | ✅ 一致 |
| S8 unconstitutionalKills 阈值 | workflow.js:785 | ✅ 一致 |
| M6 PatchLoop 阶段 | workflow.js:833-895 | ✅ 实现正确（含 2 个 P1 边缘 bug 见下） |
| SYNTHESIS_PROMPT 签名变更 | workflow.js:414, 814 | ✅ 同步无悬空 winner 引用 |

**v6.1 修复全部正确实施，未引入新回归。但 P0 修复未触及的 v6.0 旧 P1 案 + M6 实施边缘暴露了 13 条新发现。**

---

## 致命漏洞（按优先级 P0→P3，13 案 → CrossAttack 后 12 幸存 1 淘汰）

### 🚨 P0 致命（3 条，4 队共认）

**S1. 空宪法颁布**（4 队共认：T0/T1/T2/T3）
- 位置: `workflow.js:580-590`
- 现象: 议会团灭（passed=[], eternityPassed=[]）仍颁布 `constitution = {articles:[], ...}`，下游假性"严格"遵守空宪法
- 攻击: 恶意议程让所有条款 fail → 0 条款宪法 → Verify 退化为纯 refuted 计数
- CrossAttack: T0/T1/T2/T3 全 agree, T1 降级 P3 opt (T1 说"实际概率极低")，3 维持 P0
- 修: `workflow.js:579` 前加 `if (passed.length===0 && eternityPassed.length===0) { constitution=null; constitutionBlock=''; log('⚠️ 0 条款降级'); }`

**S5c. S5 修复不彻底 — vote-level OR 非 claim-level hard veto**（T3 owner，3 队 agree + 1 队 refuted）
- 位置: `workflow.js:720-723`
- 现象: `refuted = v.refuted || v.unconstitutional` 是 vote-level OR。1违宪+1refuted+3approve=幸存
- 反例: T1 票数例证 = `valid.length=5, refuted=2 < 3 ✓, (5-2)=3 > 2 ✓` → survives
- 违背 SKILL.md:24 "S5 违宪票数学化 — 为真但越界照样淘汰的硬约束" 承诺
- CrossAttack: T0/T1/T3 agree (P0), T2 refuted (P3 opt, 主张 N-vote democracy)
- 修: `workflow.js:720` 后加 `const hasUnconstitutional = valid.some(v => v.unconstitutional)`, `survives = !hasUnconstitutional && ...`

**S9. 预算饿死 — global fetchSlots + high 豁免 + 空 claims 不扣分**（T1+T3 co-owner）
- 位置: `workflow.js:266` (全局 fetchSlots) + `workflow.js:644-647` (high 豁免) + `workflow.js:670-677` (空 claims 不扣)
- 现象: 4 队共享 15 slots 池 + relevance 自报 high (relRank=0) 永远豁免 + 失败/0 claims URL 仍占 slot
- 攻击: 1 队自报 6 条 high + 灌空 URL → 烧光预算 + 0 成本
- CrossAttack: T0 降 P1, T1 降 P1, T2 维持 P0, T3 升 P0+1
- 修: fetchSlots 改 per-team 配额 `Math.floor(MAX_FETCH/teamDefs.length)` + 去掉 high 豁免

### P1 致命（5 条）

**M4. 永恒条款 text 严格匹配 + 落选静默**（4 队共认）
- `workflow.js:546` `find(v=>v.text===e.text)` 严格匹配；line 549 filter 丢弃失败项；line 587 minority_report 仅含普通 failed articles
- 攻击: 委员会微调 eternity 措辞 → 所有 4 议员 vote 静默失效
- 修: eternityProposal 加 id (E1..En) + 落选写 `minority_report.eternity_failed`

**M6-ctx. prevPatches 丢上下文**（T1 owner，3 队 agree）
- `workflow.js:880` `prevPatches = accepted` 只留上轮
- Round 3 看不到 Round 1 已采纳
- 修: `prevPatches = [...prevPatches, ...accepted]` (一行)

**M6-ver. PATCH_VERIFY 不传 prevPatches**（T1 owner，3 队 agree）
- `workflow.js:864` 调用只传 `(patch, v, TASK)`；prompt 第 475 行问"是否与已采纳的 patches 冲突"但无数据
- 修: PATCH_VERIFY_PROMPT 签名加 prevPatches + prompt 注入已采纳列表

**S7. SYNTHESIS "Evidence: undefined"**（T0 owner，3 队 agree）
- `workflow.js:420` 引用 `c.evidence` 但 EXTRACT_SCHEMA claim 字段无 evidence
- 跨队融合后所有 confirmed claims 都触发字面 "undefined" 输出
- 修: 改用 `c.verdicts.filter(v=>!v.refuted).sort(...).evidence` 或 c.quote

**S3. minority_report 不进 constitutionBlock**（T0 owner，3 队 agree）
- `workflow.js:591-599` 拼接跳过 minority_report
- SYNTHESIS_PROMPT 要求 caveats 引用少数意见但 agent 拿不到数据
- 修: constitutionBlock 末尾追加 `### 少数意见(2-2 条款) + map` 块

### P1 优化（2 条）

**PL-def. CONFIG.patchLoop 默认 true vs SKILL.md 矛盾**（T2 owner，2 agree + 1 refuted + 1 opt）
- `workflow.js:835` `if (CONFIG.patchLoop !== false)` 默认开；SKILL.md:234 "不适用普通研究类"
- 影响: 普通研究场景默默多 12-36 calls
- 修: 翻转默认 `=== true` opt-in + SKILL.md:158 同步注释

**M2-cmp. F0 兜底 5 分 + 跨队融合 + PatchLoop = 刷分通道**（T3 owner，2 agree + 1 refuted）
- `workflow.js:751` `problemPoints[c.subProblemId] ?? 5` + M2 跨队融合放大
- 攻击: 1 队专攻 F0 模糊边缘 claim → 30×5×impW×confW ≈ 200+ 分
- 修: `if (!c.subProblemId || c.subProblemId==='F0' || !problemPoints[c.subProblemId]) continue`

### P2-P3（2 条）

**S4. CONFIG 校验缺失**（T1+T2 co-owner，1 refuted T3）
- `workflow.js:25-26` 无上下界校验，可配必死局（votes=2+refute=3）或全活局（votes=5+refute=6）
- 修: 加 clamp `Math.min(Math.max(Number(CONFIG.votes)||5, 1), 10)`

**PL-snp. PATCH_PROMPT 主问题字符串嗅探脆弱**（T2 owner，2 agree + 1 refuted）
- `workflow.js:449` "主问题提到 skill/workflow.js/致命漏洞/可优化" 关键词过窄
- 修: 扩展关键词集合（含 audit/workflow/v6/refactor 等）

---

## CrossAttack 淘汰（1 案）

**M6-zc. PatchLoop 零成本攻击**（T3 owner）— ❌ **被 T2+T3 联合反驳淘汰**
- T2: "maxItems=3 + clamp 1-3 已防护，最多 72 calls 而非 120；agent 调用消耗 token 不是 correctness DoS"
- T3: "2/3 通过率与制宪会议 SUPERMAJORITY=3 一致；prompt 强 4 检查 + 默认 approved=false 通过率 <30%"
- 0 维持 P0，T2 降 P2，T3 降 P2

---

## PatchLoop M6 实施验证（4 队提 11 patches）

| # | Team | FlawId | 修法 | 状态 |
|---|------|--------|------|------|
| 1 | T0 | S1 | 5 行 if 守卫 + DEGRADED constitution 对象 | 待 apply |
| 2 | T0 | S5c | AND 三联条件 (approved≥3 && rejected<1 && refuted<2) | 待 apply (但 hardcode 阈值) |
| 3 | T0 | S9 | per-team 配额 + 去掉 high 豁免 + PATCHLOOP_RESERVE=20 | 待 apply |
| 4 | T1 | M6-ctx | `prevPatches = [...prevPatches, ...accepted]` | ✅ 即时验证正确 |
| 5 | T1 | M6-ver | PATCH_VERIFY_PROMPT 签名加 prevPatches + prompt 注入块 | ✅ 即时验证正确 |
| 6 | T2 | PL-def | 翻转默认 `=== true` opt-in + SKILL.md 同步 | ✅ 即时验证正确 |
| 7 | T2 | PL-snp | 扩展关键词集合（含 audit/workflow/v6/refactor 等） | ✅ 即时验证正确 |
| 8 | T2 | S1 | 5 行 if 守卫（同 T0） | 重复 #1 |
| 9 | T3 | S5c | `hasUnconstitutional` 硬 veto | ✅ 即时验证正确（最简方案） |
| 10 | T3 | M2-cmp | F0 不计分（surv/rej 都加 continue） | ✅ 即时验证正确 |
| 11 | T3 | M6-ctx | PATCH_VERIFY prevPatches（同 #5） | 重复 #5 |

**共识度**:
- S1: 2 队提同款 (T0+T2) — 强共识
- S5c: 2 队提 (T0+T3)，T0 阈值 hardcode 风险大，T3 方案更稳
- M6-ctx: 2 队提 (T1+T3) — 强共识
- M6-ver: 2 队提 (T1+T3) — 强共识
- S9/PL-def/PL-snp/M2-cmp: 各 1 队独家

**M6 实施评估**: 提议阶段运转正常（4 队 11 patches），但 PatchLoop 本身的 prevPatches bug 暴露了 2 条 P1 致命 — 表明 M6 "兑现了"但"兑现得不够好"。**真正的多轮修补还需修 M6-ctx + M6-ver 两条 P1。**

---

## v6.1 修复优先级（v6.2 升级建议）

### P0 必须修（4 条）
1. **S1 空宪法降级守卫** (T0+T2 同款): `if (passed.length===0 && eternityPassed.length===0) { constitution=null; ... }` — 5 行
2. **S5c S5 硬 veto** (T3 推荐): `if (valid.some(v => v.unconstitutional)) { survives=false; isRefuted=true }` — 3 行
3. **S9 预算 per-team 配额** (T0): fetchSlots 改 Object/Map, 去掉 high 豁免 — 8 行
4. **M6-ctx prevPatches 累积** (T1+T3 同款): `prevPatches = [...prevPatches, ...accepted]` — 1 行

### P1 推荐修（4 条）
5. **M6-ver PATCH_VERIFY prevPatches** (T1+T3 同款): 签名+prompt+call site 3 处改 — 6 行
6. **M4 永恒条款 id 化** (4 队共认): COMMITTEE_SCHEMA 加 id + 落选进 minority_report — 10 行
7. **S7 Evidence undefined** (T0 owner): 改用 c.verdicts 最佳未反驳 evidence — 1 行 + 1 helper
8. **S3 minority_report 进 constitutionBlock** (T0 owner): 拼接末尾追加 4 行 — 4 行

### P2 可选修（3 条）
9. **PL-def CONFIG.patchLoop 默认翻转** (T2 owner): `=== true` opt-in + SKILL.md 同步
10. **M2-cmp F0 不计分** (T3 owner): 2 处加 continue
11. **S4 CONFIG 校验** (T1+T2 co-owner): clamp + log

### 不修（接受 P3）
- PL-snp 嗅探脆弱（key 集合扩展是 cosmetic，结构性问题需 taskType 字段）
- M6-zc 已淘汰（maxItems=3 + clamp 已防护）
- 文档/配置杂项

---

## 竞赛元结论

- **v6.1 修复 5 条 P0 中 4 条正确 + 1 条不彻底 (S5c)**: vote-level OR 实现但缺 claim-level hard veto
- **v6.0 旧 P1 案 (M4/S1/S3/S9) 4 队重新确认 100% 仍未修**: 4 案跨两轮审计零分歧
- **M6 兑现但 2 实施 bug (M6-ctx/M6-ver)**: 多轮修补机制本身需要被修补
- **零淘汰 M6-zc**: T2+T3 联合反驳认为 72 calls 上限 + maxItems=3 + 2/3 通过率 = 可接受
- **v6.2 建议**: P0 4 条 + P1 4 条 = 8 条总计 38 行新代码完成 v6.2

## v6.1 → v6.2 升级日志（待用户拍板）

- **2026-08-22 v6.2**: 自审计二轮后修复 4 条 P0 致命 + 4 条 P1 致命
  - P0 S1: 5 行 if 守卫 (空宪法降级)
  - P0 S5c: 3 行 hasUnconstitutional 硬 veto
  - P0 S9: 8 行 fetchSlots 改 per-team 配额
  - P0 M6-ctx: 1 行 prevPatches 累积
  - P1 M6-ver: 6 行 PATCH_VERIFY 传 prevPatches
  - P1 M4: 10 行 永恒条款 id 化
  - P1 S7: 1 行 + helper 最佳未反驳 evidence
  - P1 S3: 4 行 minority_report 进 constitutionBlock
  - 总计 38 行新代码
