# adversarial-research v6.2 自审计求解赛 — 第三轮最终报告

**日期**: 2026-08-22 · **赛制**: 4队 Assess (T0架构/T1致命/T2工程/T3边界) + CrossAttack 综合
**v6.2 起点**: P0 修复 S1/S5c/S9 + P0 M6-ctx + P1 M6-ver
**投票结果**: 4 队共提 9+7=16 finding, 跨队共识度 T0=4/T1=5/T2=3/T3=8 (T3 边界操纵派最锋利)

---

## 排行榜（按 finding 数量 × severity × 跨队共识度加权）

| 名次 | 队伍 | 提报 | 代表作 |
|------|------|------|--------|
| 🥇 1 | T3 边界操纵派 | 8 | M6-ver.1 长 title DoS (P0) + S5c.1 单评委独裁 (P1) + S5c×S8 双计票失真 (P1) |
| 🥈 2 | T1 致命漏洞猎手 | 5 | NEW-1 S9 砖化配置 (P1) + 永恒条款根因反例 + PatchLoop 多轮真实测试 |
| 🥉 3 | T0 架构审查派 | 4 | N1 16+队0预算 (P0) + N2 指标 stale (P1) + 7 v6.1 finding 全部仍处待 v6.3 |
| 4 | T2 工程实现派 | 3 | 行号 92% 漂移 (P0) + 版本元数据不一致 (P0) + S1 嵌套 if/else 6 层完美配对 |

**灵感奖**: T0 架构审查派 — 准确追溯 v6.2 5 patch 全部正确实施 + 揭露 v6.2 自身引入的 3 P0 bug（N1/M6-ver.1/S9 砖化），同时确认 6 v6.1 修复未误伤

---

## v6.2 Patch 回归测试（4 队共认）

| 修复 | 位置 | 状态 |
|------|------|------|
| S1 空宪法降级 | workflow.js:583-610 | ✅ 6层if/else完美配对，5 阶段全部 `(constitutionBlock ? ... : "")` 三元守卫 |
| S5c claim-level 硬 veto | workflow.js:735-739 | ✅ hasUnconstitutional 逻辑严密，但 1 评委独裁设计风险（NEW-4 P2） |
| S9 per-team fetchSlots | workflow.js:267, 656-662 | ⚠️ 正确但引入 0 预算边界 bug (N1 P0) + 20% 预算黑洞 (N5 P2) |
| M6-ctx prevPatches 累积 | workflow.js:896 | ✅ 累积验证正确，Round 3 看到 Round 1+2 |
| M6-ver PATCH_VERIFY 传参 | workflow.js:464, 879 | ⚠️ 正确但 PATCH_SCHEMA.title 无 maxLength (M6-ver.1 P0 DoS) + Round 1 fallback 缺失 (NEW-5 P3) |

**v6.2 5 patch 代码层 100% 实施正确，但**：
- S9 修复未考虑边界（MAX_FETCH<teams 或 teams>=16 时 0 预算）
- S5c 修复过激（1 票 unconstitutional 独杀）
- M6-ver 修复引入了 PATCH_SCHEMA 无 maxLength 的新攻击面
- 5 处文档行号引用 13/14 不准（92% 漂移）
- 3 处版本元数据未升级（workflow.js description/header + SKILL.md 标题）

---

## 致命漏洞清单（4 队共认 16 finding，按 P0→P3 排序）

### 🚨 P0 致命（3 条新 + 1 旧）

**M6-ver.1. PATCH_SCHEMA.title 无 maxLength → 长 title DoS**（T3 owner，4 队共认）
- 位置: `workflow.js:202-218` PATCH_SCHEMA + `workflow.js:464-476` PATCH_VERIFY_PROMPT 注入块
- 攻击: Round 2 1 队提 1 patch `title = "A".repeat(8000)` (8KB) → Round 3 `prevPatches` 注入块 ≈ 8.6KB → 评委 prompt 自身 ~2KB + 注入块 > 8K context → 评委模型截断/null → approved=0/3 → 整轮修补全废
- 修: `title: { type: "string", maxLength: 200 }` + 服务端 LABEL_CAP 截断（2 行）

**N1 + NEW-1. S9 0 预算边界（2 个角度同根因）**（T0+T1 共同发现）
- 位置: `workflow.js:267` `Math.floor(MAX_FETCH / Math.max(TEAM_IDS.length, 1))`
- 角度 1 (T0 N1): `CONFIG.teams.length >= 16` → 全部 0 slots → 0 URLs → 早退
- 角度 2 (T1 NEW-1): `MAX_FETCH < teamCount`（如 3/4=0）→ 整系统砖化，无报错
- 攻击: 恶意/手滑 config `{maxFetch: 2}` 或 `{teams: ['T0','T1',...'T15']}` → 静默不产出
- 修: 用余数分配（保证 sum=MAX_FETCH）+ 配 S4 clamp `Math.max(MAX_FETCH, teamDefs.length)`（5 行）

**M4. 永恒条款 text 严格匹配 + 落选静默**（v6.1 旧 P1, T1 反例构造 升级 P0）
- 位置: `workflow.js:550` `(b.eternityVotes || []).find(v => v.text === e.text)` + `workflow.js:597` `minority_report` 仅含 `failed`
- 反例: committee 提案 `text = "所有 claim 必须可证伪且带来源"`（有空格），4 议员 vote 时 text 去空格 → 4 票 `find returns undefined` → `votes=[]` → `passed=false` → 永恒条款 0 票静默蒸发
- 严重性升级理由: 这是"永恒条款存在性 bug"，永恒条款是元规则保护层，蒸发等于整个制宪机制的元规则丢失
- 修: COMMITTEE_SCHEMA 加 `id: E1..En` + 落选写 `minority_report.eternity_failed`（10 行）

### P1 致命（8 条新 + 3 条 v6.1 旧）

**N2. unconstitutionalKills 指标 stale**（T0 owner，2 队 agree）
- 位置: `workflow.js:800` `killed.filter(c => (c.unconstitutionalVotes || 0) >= REFUTATIONS_REQUIRED).length`
- 问题: S5c 修复后 1 票 unconstitutional 即可 kill，但 S8 仍要求 ≥3 票违宪才计入 → 1-2 票违宪 kills 全部漏统
- 影响: 自审计报告 `unconstitutionalKills` 数字系统性低估 1/3
- 修: `unconstitutionalKills = killed.filter(c => c.unconstitutionalVotes > 0).length`（1 行）

**S5c.1. 单评委独裁**（T3 owner，3 队 agree）
- 位置: `workflow.js:735-739`
- 攻击: 5 票中 1 票 `unconstitutional=true` + 4 票 approve → hasUnconstitutional=true → 整 claim 死。**任何 1 评委可零成本独杀**
- 修: `if (unconstitutional >= Math.ceil(VOTES_PER_CLAIM / 2)) hasUnconstitutional=true` quorum 守卫（1 行）

**S5c.4. 错误默认穿透**（T3 owner，2 队 agree）
- 位置: `workflow.js:735-739`
- 攻击: 4/5 评委 errored → `valid=1, hasUnconstitutional=false` → survives=false 但 `isRefuted=false` → 落 `unverified` 而非 `killed` → 违宪 claim 复活
- 修: `if (errored > VOTES_PER_CLAIM/2) isRefuted = true`（1 行）

**S9.2. dupes 不扣 slot = 配额溢出**（T3 owner，2 队 agree）
- 位置: `workflow.js:650-653` dedup 路径先于 slot 检查，不扣 slot
- 攻击: 1 队返回 6 URL 全是 dupes → 该队 novel=0 但 teamSlots 仍 3 → 其他队看到预算已被该队"占用"
- 修: dupes 路径也扣 slot 或计入 `budgetDropped`（1 行）

**S5c×S8. 双计票失真**（T3 owner，2 队 agree）
- 同 N2, 不同表述角度

**S1×S5c. cascade 失联动**（T3 owner，1 队 agree）
- 位置: `workflow.js:585` constitution=null 后 Verify 阶段评委仍可用 `unconstitutional` 字段
- 问题: 评委不知道没有宪法，仍可能填 `unconstitutional=true` → S5c 仍触发
- 修: constitutionBlock 空时 Verify prompt 注入 "无宪法模式,跳过 unconstitutional 字段"（1 行）

**M2-cmp. F0 兜底 5 分刷分通道**（T3 owner，2 队 agree）
- 位置: `workflow.js:766, 770` `problemPoints[c.subProblemId] ?? 5`
- 攻击: 1 队专攻 F0 模糊边缘 claim → 30×5×impW(3)×confW(1) ≈ 450 分刷分
- 修: `if (!c.subProblemId || c.subProblemId === "F0" || !problemPoints[c.subProblemId]) continue`（1 行 × 2 处）

**NEW-2. PatchLoop 轮内去重缺失**（T1 owner）
- 位置: `workflow.js:868` flatPatches 后无去重
- 攻击: 4 队协调提同款 patch → 4 accepted → Round 2 票面 4 行重复
- 修: `seen = new Set()` filter by `flawId+title`（3 行）

**M4/S7/S3. v6.1 旧 P1 三连修**（4 队共认）
- M4 永恒条款 id 化（10 行）
- S7 SYNTHESIS Evidence undefined → `c.verdicts.filter(v => !v.refuted).sort(...).evidence || c.quote`（1 行）
- S3 minority_report 进 constitutionBlock 拼接末尾（4 行）

### P2 优化（5 条）

- N4 (T0) M6-ctx 标签 "上一轮" 应改 "已采纳"（cosmetic）
- N5 (T0) S9 floor 浪费 20%（设计选择，可改 ceil）
- S5c.2 误判无 reason 强制（schema 缺 required reason）
- S5c.3 S5c/S6 互相屏蔽无定义
- NEW-3 (T1) SKILL.md 行号同步（文档）
- NEW-5 (T1) PATCH_VERIFY prevPatches Round 1 fallback 占位
- NEW-6 (T1) SKILL.md 标题统一 v6.2
- PL-def (T0) CONFIG.patchLoop 默认翻转 opt-in
- S4 (T0/T1) CONFIG clamp

### P3（接受）

- N6 (T0) M6 同 round 互相盲问
- N7 (T0) S1 else 缩进
- S5c.5 refuted 累加（易混淆但非 bug）
- S9.3 浪费 slot 不回收
- S9.4 relRank 排序
- S9.5 Map 不重置
- M6-ctx.2 自指循环膨胀
- M6-ctx.3 allPatches 不传 synthesis
- M6-ver.2 注入块不显示 diff
- PL-snp 关键词窄

---

## 跨案复合洞察

1. **v6.2 净效果**: 从 v6.1 的 13 finding 减少到 16 finding（v6.2 自身引入 9 条新 finding + 7 条 v6.1 旧 finding），但**v6.2 的 9 条新 finding 严重性更高**（3 P0 中 2 条 v6.2 引入）。M6 兑现但实施未优化
2. **S9 修复路径不完整**: v6.2 改 fetchSlots 分配但未考虑 0 预算边界（MAX_FETCH<teams 或 teams>=16）。修分配算法 + S4 clamp 必须联修
3. **S5c 民主 vs 独裁哲学冲突**: 4 队对此严重性评估不一致（T2 P3 opt, T0/T3 P0, T1 P2）。T1 反思"用户例子有误"后承认存在设计风险但非 bug。需要 quorum + 错误穿透两项修补实现硬约束又防独裁
4. **PatchLoop 自身需修补**: M6 兑现了但暴露 3 条 P1-P3 自身 bug。M6-ver.1 (P0 DoS) 最危险

---

## v6.2 → v6.3 升级建议（用户授权 14 行 v6.3 patch + 新发现额外建议）

### v6.3 核心（M4+S3+S7 用户授权的 14 行）
1. **M4 永恒条款 id 化** (10 行): COMMITTEE_SCHEMA + minority_report.eternity_failed
2. **S3 minority_report 进 constitutionBlock** (4 行): 拼接末尾追加
3. **S7 SYNTHESIS Evidence fix** (1 行): 改用 c.verdicts 最佳未反驳 evidence

### v6.3 强烈建议追加（对抗验证 新发现）
4. **M6-ver.1 PATCH_SCHEMA maxLength** (2 行): 防 8KB title DoS
5. **S9 砖化修复** (5 行): 余数分配 + S4 clamp
6. **unconstitutionalKills 指标修复** (1 行): `> 0` 替代 `>= REFUTATIONS_REQUIRED`
7. **S5c.1 quorum + S5c.4 错误穿透** (2 行): `unconstitutional >= ceil(VOTES/2)` + `errored > VOTES/2` isRefuted

合计 7 patches / 25 行新代码 = v6.3 完整升级

### 不修（接受 P2-P3）
- N4/N5/N6/N7 文档 + cosmetic
- S5c.2/3 哲学冲突（T1 反思后承认非 bug）
- S9.1/3/4/5 design choices
- M6-ctx.2/3 + M6-ver.2 follow-up
- PL-def / PL-snp / S4 已知 finding（不在本轮范围）

---

## 竞赛元结论

- **v6.2 5 patch 代码层 100% 正确**（T0/T1/T2 独立验证），但**v6.2 自身引入 9 条新 finding**（含 3 P0 + 6 P1）
- **v6.1 旧 7 finding 中 4 条仍是 P0/P1**（M4 升级 P0，S7/S3 维持 P1，PL-def/M2-cmp/S4 仍 P1-P2）
- **M6 兑现了多轮修补但自身需修补**（M6-ver.1 DoS + M6-ctx label + M6-ver fallback）
- **S9 修复路径不完整**（0 预算边界），S5c 修复过激（1 票独裁）
- **文档同步严重脱节**（行号 92% 漂移 + 版本元数据 3 处不一致）
- **建议**: v6.3 应用 7 patches / 25 行 = 用户授权 14 行 + 强烈建议 11 行新发现修补
