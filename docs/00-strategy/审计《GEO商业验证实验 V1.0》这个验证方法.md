# 审计《GEO商业验证实验 V1\.0》这个验证方法

对，而且这一次审计比前两次更重要。

因为我们刚才已经从“商业模式”走到了“实验设计”。如果实验设计本身有偏差，后面得到的所谓“验证结果”也可能是假的。

所以这次我不审计 GEO 商业模式本身，而是审计：

> **《GEO商业验证实验 V1\.0》这个验证方法，能不能真的证明商业模式成立。**
> 
> 

我会继续用“反对者”视角。

---

# 一、先给结论

上一轮的验证方案，我给：

> **方向正确，但实验设计还不能直接执行。**
> 
> 

最大的问题不是“5–10个客户太少”。

真正的问题是：

> **我们目前设计的实验，可能证明“有人愿意买你的服务”，却证明不了“这个商业模式可以规模化”。**
> 
> 

甚至还有一个更危险的问题：

> **我们可能把“你的个人专业能力”验证成了“GEO产品能力”。**
> 
> 

这两个东西必须拆开。

所以我建议：

**暂缓《Product \& Pricing V1\.0》**。

先把验证实验本身修正。

---

# 二、第一刀：5–10个客户真的能证明商业模式吗？

我们上一轮说：

> 5–10个付费客户。
> 
> 

这作为**探索性实验**可以。

但如果我们得出：

> “5个客户中3个续费，所以商业模式成立。”
> 
> 

这是错误的。

为什么？

因为5个客户可能都是：

- 你认识的人

- 对 GEO 特别感兴趣的人

- 对 AI 特别敏感的人

- 因为相信你个人而购买的人

这叫：

> **Selection Bias（选择偏差）**
> 
> 

他们不是随机客户。

所以：

> 3/5续费
> 
> 

只能说明：

> **这批高意愿客户中存在商业价值。**
> 
> 

不能证明：

> **普通市场具有同样需求。**
> 
> 

---

# 三、第二刀：我们的“首批客户”可能天然不代表市场

我们之前建议：

> SaaS / B2B / 高客单价服务 / DTC。
> 
> 

这个方向没错。

但还有一个更重要的问题：

### 谁来获得这些客户？

如果客户全部来自：

> 你的个人关系、SEO圈、朋友、熟人介绍。
> 
> 

那么我们验证的是：

> **Founder\-led sales**
> 
> 

而不是：

> **可复制获客。**
> 
> 

这对未来渠道模型非常重要。

---

# 四、所以必须增加一个变量：

## Customer Acquisition Source

每个客户必须标记：

```Plain Text
Founder network
Cold outbound
Inbound
Partner
Community
Referral
Existing relationship
```

否则最后可能出现：

> 10个客户都买了。
> 
> 

但实际上：

> 10个都是你亲自谈下来的。
> 
> 

那么渠道模型仍然没有被验证。

---

# 五、第三刀：我们所谓“Pilot”可能太容易卖

这是一个非常隐蔽的问题。

假设你对客户说：

> “我现在正在做一个GEO系统，希望你成为早期客户，价格优惠。”
> 
> 

客户可能因为：

> 支持你
> 
> 

而购买。

这并不能证明：

> 客户在正常市场条件下愿意购买。
> 
> 

所以 Pilot 必须区分：

### Research Customer

帮助你验证产品。

和：

### Commercial Customer

按照正常商业条件购买。

后者的证据价值远高于前者。

---

# 六、所以我要修改一个关键原则

第一批可以有：

> **Early Adopter Pricing**
> 
> 

但是必须满足：

> **客户是真付款，不是友情价/免费。**
> 
> 

而且最好明确：

> Pilot结束后的标准价格。
> 
> 

例如：

```Plain Text
90-Day Pilot
$X

Post-Pilot:
$Y/month
```

这样第三个月才真正有意义。

因为客户知道：

> “如果继续，就不是这个优惠价格了。”
> 
> 

---

# 七、第四刀：90天本身是一个假设

我们刚才把：

> 90\-Day GEO Growth Pilot
> 
> 

设计得很漂亮。

但我要问：

> **为什么一定是90天？**
> 
> 

这是一个未经验证的假设。

有些 GEO 变化：

> 几周就能观察。
> 
> 

有些：

> 可能需要几个月。
> 
> 

有些：

> 根本无法在90天内证明商业结果。
> 
> 

因此：

> 90天不是事实，而是实验周期假设。
> 
> 

---

# 八、真正应该定义的是“Evidence Window”

也就是说：

不要先决定：

> 90天。
> 
> 

而应该先问：

> **我们希望观察的变化，最短需要多久？**
> 
> 

例如：

### Measurement

可能几天就可以。

### Visibility change

可能需要数周。

### Citation change

可能更慢。

### AI Referral

可能需要更长时间。

### Lead

取决于流量。

### Revenue

可能根本不是90天能够证明。

因此最好设计成：

```Plain Text
Week 0
Baseline

Week 2
Early Signal

Week 4
First Optimization Review

Week 8
Midpoint

Week 12
Commercial Review
```

而不是简单：

> Day 1 → Day 90。
> 
> 

---

# 九、第五刀：我们还没有真正定义“成功”

上一轮说：

> Visibility提升。
> 
> 

问题来了：

### 提升多少？

比如：

> 10% → 12%
> 
> 

算成功吗？

如果：

> 10% → 30%
> 
> 

当然很漂亮。

但如果：

> 10% → 30%
> 
> 

客户业务：

> Leads 0 → 0
> 
> 

怎么办？

所以不能只定义：

> “指标变好。”
> 
> 

必须定义：

# Evidence Hierarchy

---

## Level 0

数据能稳定采集。

---

## Level 1

Visibility改善。

---

## Level 2

Citation改善。

---

## Level 3

AI Referral出现/增长。

---

## Level 4

AI\-assisted Lead出现。

---

## Level 5

商业机会/Revenue出现。

---

这里最重要的是：

> **不同客户达到不同层级，也可以算成功。**
> 
> 

不能要求所有客户都达到Revenue。

---

# 十、但是还有一个更大的问题：

## GEO变化到底是不是你造成的？

假设：

```Plain Text
Month 1:
Visibility = 10%

Month 3:
Visibility = 30%
```

我们很容易说：

> “GEO优化成功。”
> 
> 

但实际上可能是：

- AI模型更新

- Prompt变化

- 竞争对手变化

- 网站自然增长

- 新内容发布

- Google索引变化

- 第三方媒体报道

导致。

这叫：

> **Attribution Problem（归因问题）**
> 
> 

这是整个 GEO 商业化里面非常重要的问题。

---

# 十一、因此我们的实验不能只有 Before / After

至少要记录：

### Prompt固定组

一部分 Prompt：

> 整个实验期间保持不变。
> 
> 

---

### Exploration组

另一部分：

> 持续增加新Prompt。
> 
> 

这样才能区分：

> 原有Visibility变化
> 
> 

和：

> 新市场覆盖。
> 
> 

---

# 十二、最好进一步设计“Holdout”

例如：

```Plain Text
100 prompts

80 = Optimization Group
20 = Holdout Group
```

80个进行优化。

20个尽量不针对性优化。

然后观察：

> 两组变化是否不同。
> 
> 

这比简单：

> “优化前10%，优化后30%”
> 
> 

科学得多。

---

# 十三、但是这里又出现一个现实问题

你不能真的控制：

> ChatGPT / Perplexity / Gemini
> 
> 

所以严格意义上的随机对照实验很难。

因此我们不能把 GEO 实验包装成：

> “严格因果证明。”
> 
> 

更专业的说法应该是：

> **Longitudinal evidence \+ controlled prompt sets \+ documented interventions**
> 
> 

即：

> **纵向证据 \+ 控制Prompt集合 \+ 干预记录。**
> 
> 

这反而符合你现在一直强调的：

> Measurement Protocol。
> 
> 

---

# 十四、第六刀：我们可能把“客户执行”错误归因给GEO

例如你建议客户：

> 写10篇内容。
> 
> 

客户写了。

同时：

> 修改网站结构。
> 
> 

又做了。

又：

> 获得5个媒体引用。
> 
> 

然后Visibility提升。

那么到底是哪一个动作产生作用？

如果你没有记录：

> Intervention Log
> 
> 

以后你的方法论无法积累。

---

# 十五、所以必须增加：

# GEO Intervention Log

每一个客户都记录：

然后 Measurement：

> 什么时候发生变化？
> 
> 

这会成为你未来真正的：

> **GEO Knowledge Base**
> 
> 

---

# 十六、第七刀：我们上一轮过早把“续费”作为最重要指标

续费当然重要。

但它不是唯一指标。

因为：

### 客户不续费

可能是：

> GEO没价值。
> 
> 

也可能是：

> 客户现金流出问题。
> 
> 

或者：

> 公司战略调整。
> 
> 

或者：

> 客户内部没人执行。
> 
> 

反过来：

### 客户续费

也不一定证明：

> GEO真的有效。
> 
> 

可能只是：

> 客户喜欢你。
> 
> 

所以必须同时看：

```Plain Text
Behavior
+
Outcome
+
Retention
```

而不是只看Retention。

---

# 十七、第八刀：客户满意度也不够

上一轮我们用了：

> Customer Satisfaction
> 
> 

这也不够。

客户可能说：

> “很好。”
> 
> 

但不续费。

所以更有价值的是：

### Willingness to Pay Again

甚至：

> **在恢复标准价格后，客户是否继续。**
> 
> 

这才是商业证据。

---

# 十八、第九刀：我们还没有验证“客户真正买的是什么”

这是我认为上一轮最大的遗漏之一。

客户购买之后，我们必须问：

> **如果只能保留一个功能，你最愿意保留哪个？**
> 
> 

可能出现：

### A

“Visibility dashboard。”

### B

“Competitor intelligence。”

### C

“GEO recommendations。”

### D

“你帮我做优化。”

### E

“AI leads。”

这个答案会直接决定：

> Product V1\.0。
> 
> 

否则我们可能先做了一套：

> 我们认为客户需要的产品。
> 
> 

而不是：

> 客户真正愿意买的产品。
> 
> 

---

# 十九、第十刀：我们甚至不应该把“GEO产品”当成单一产品

现在看起来可能存在三种完全不同的客户需求：

### 类型A

> “告诉我AI里有没有我。”
> 
> 

这是 Measurement。

---

### 类型B

> “告诉我为什么没有我。”
> 
> 

这是 Diagnostic。

---

### 类型C

> “你帮我把这个问题解决。”
> 
> 

这是 Managed GEO。

这三个产品：

> **客户价值、价格、交付成本完全不同。**
> 
> 

所以未来产品矩阵很可能不是：

> Basic / Pro / Enterprise
> 
> 

而是：

> **Measure / Diagnose / Grow**
> 
> 

这点现在还不应该定死，但值得重点验证。

---

# 二十、第十一刀：我们之前的Partner实验也存在偏差

我们说：

> 3–5个Partner。
> 
> 

这个数量作为探索可以。

但最大的错误可能是：

> 只测试“Partner愿不愿意卖”。
> 
> 

应该测试：

# Partner Independence

也就是：

> **没有你亲自出面，他能不能卖出去？**
> 
> 

这是关键。

如果：

```Plain Text
Partner
↓
客户
↓
你出席Demo
↓
你解释GEO
↓
你解决异议
↓
你成交
```

然后我们说：

> “Partner销售成功。”
> 
> 

这是假的。

---

# 二十一、所以Partner实验必须分层

### Level 1

你辅助成交。

> ❌ 只是销售协作。
> 
> 

### Level 2

Partner主导销售，你支持技术。

> 🟡 有价值。
> 
> 

### Level 3

Partner独立完成销售。

> 🟢 真正的渠道能力。
> 
> 

### Level 4

Partner主动寻找客户并持续销售。

> 🟢🟢 真正可规模化。
> 
> 

---

# 二十二、第十二刀：我们还没有验证Partner为什么不自己做

这是渠道模型必须回答的。

我们说：

> “自己开发太贵。”
> 
> 

这是我们的假设。

Partner可能回答：

> “其实我招一个SEO人员就可以。”
> 
> 

那么：

> 你的平台价值就必须重新证明。
> 
> 

真正应该问Partner：

> “如果没有我们的系统，你会如何解决这个需求？”
> 
> 

然后看看答案：

- 自己开发

- 招人

- 买其他工具

- 外包

- 不做

这个问题非常有价值。

---

# 二十三、第十三刀：Partner毛利30%不一定足够

我们之前算：

> $899售价 → $599采购 → $300毛利。
> 
> 

但真正应该算：

# Partner Contribution

```Plain Text
Gross Margin
-
Sales Cost
-
Support Cost
-
Account Management
-
Customer Acquisition
```

例如：

```Plain Text
毛利 $300

Sales Cost $100
Support $50
CAC Amortization $80

真实贡献：
$70
```

那么这个Partner很可能不愿意持续卖。

所以：

> **Partner economics必须按“每客户贡献利润”计算，而不是简单毛利率。**
> 
> 

---

# 二十四、第十四刀：HQ也有一个隐藏成本

你现在可能认为：

> “系统自动化以后成本很低。”
> 
> 

但不要忘了：

### Exception Handling

当出现：

- AI模型变化

- Collector失败

- Citation解析失败

- 客户特殊Prompt

- 数据异常

- 客户投诉

- GEO策略冲突

谁来处理？

如果这些问题都找你：

> Scale就会被你自己卡死。
> 
> 

所以未来必须记录：

> **Exception Rate**
> 
> 

例如：

> 100个客户中有多少需要人工介入？
> 
> 

这是一个非常关键的规模化指标。

---

# 二十五、第十五刀：我们还缺一个最重要的“反事实”

这是我建议加入实验的一个问题：

> **如果客户什么都不做，会发生什么？**
> 
> 

否则你只能看到：

> 做了GEO之后发生了什么。
> 
> 

但不知道：

> 不做会发生什么。
> 
> 

这就是：

> Counterfactual。
> 
> 

现实中很难完美获得。

但可以用：

- Holdout Prompt

- 历史数据

- Competitor baseline

- 未优化页面

- 未干预Prompt

来近似。

---

# 二十六、所以现在我会重构整个验证体系

之前我们是：

```Plain Text
Customer
→ Pilot
→ Result
→ Renewal
```

现在我认为应该升级成：

```Plain Text
BUSINESS VALIDATION
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
     Customer            GEO                 Economics
        │                  │                  │
   Willingness         Measurement       Cost-to-Serve
   to Pay              Visibility        Expert Hours
   Renewal             Citation          AI Cost
   Referral            Referral          Margin
        │                  │                  │
        └──────────────────┼──────────────────┘
                           │
                        Partner
                           │
                    Independent Sales
                           │
                    Partner Economics
```

---

# 二十七、因此我们现在真正要验证的不是一个结论

而是五个命题：

### 命题1

> **客户认为AI Search Visibility是一个值得解决的商业问题。**
> 
> 

### 命题2

> **客户愿意为持续解决这个问题付费。**
> 
> 

### 命题3

> **我们能够用可重复的Measurement证明变化。**
> 
> 

### 命题4

> **我们能够以可接受的Cost\-to\-Serve交付。**
> 
> 

### 命题5

> **第三方Partner能够在不依赖创始人的情况下销售它。**
> 
> 

只有这五个命题逐渐被证实：

> **GEO Partner商业模式才真正成立。**
> 
> 

---

# 二十八、这次审计之后，我会删掉上一版三个东西

### 删除1：

> “5个客户中3个续费 = 商业模式成立”
> 
> 

改成：

> **探索性信号，不作为最终证明。**
> 
> 

---

### 删除2：

> “90天 = 固定验证周期”
> 
> 

改成：

> **按Evidence Window设计实验。**
> 
> 

---

### 删除3：

> “Partner愿意签约 = 渠道成立”
> 
> 

改成：

> **Partner独立成交 \+ 经济模型成立 = 渠道成立。**
> 
> 

---

# 二十九、同时增加六个必须记录的指标

我建议从现在开始，无论你有没有正式客户，都把它们设计进系统：

### Customer

1. **Willingness to Pay**

### GEO

2. **Visibility / Citation Change**

### Attribution

3. **Intervention → Outcome**

### Delivery

4. **Expert Minutes / Customer**

### Customer

5. **Renewal at Standard Price**

### Partner

6. **Partner\-led Revenue**

尤其第4个：

> **Expert Minutes / Customer**
> 
> 

我认为会成为你整个 GEO 商业模型最重要的内部指标之一。

---

# 三十、最终审计结论

这次我给上一版《GEO商业验证实验 V1\.0》的评价：

> **方向：PASS**
> 
> **实验框架：需要修订**
> 
> **可以开始做实验：YES**
> 
> **可以根据实验结果直接制定商业政策：NO**
> 
> 

更重要的是，我们现在已经把商业验证从：

> “找几个客户试试看”
> 
> 

升级成：

> **验证 Customer Value \+ GEO Evidence \+ Delivery Economics \+ Partner Independence 四条证据链。**
> 
> 

而这其实与你现在整个 GEO 项目的方法论非常契合：

> **不要因为一个结果看起来不错，就直接下结论。**
> 
> 

---

## 下一步

所以我建议下一轮不要直接做“产品定价”。

而是把刚才审计后的版本正式落地成：

# 《GEO商业验证实验 V2\.0》

我会直接给出一份**可执行实验表**，包括：

- 客户招募标准

- 客户分组

- Pilot设计

- 价格实验

- Baseline Protocol

- Prompt / Holdout设计

- Intervention Log

- 结果指标

- 客户访谈问题

- 续费判定

- Cost\-to\-Serve记录

- Partner实验

- Partner独立成交测试

- PASS / FAIL / PIVOT阈值

- 最终决策树

这样下一步做的就不是“商业规划”，而是一个真正可以启动的**商业验证项目**。

好。我们不再继续讨论“商业模式应该长什么样”，直接把它改造成一套**可以真正执行、能够产生决策证据的《GEO商业验证实验 V2\.0》**。

这版的核心变化只有一句话：

> **不是验证“有没有人喜欢 GEO”，而是验证：陌生客户是否愿意按真实价格持续付费，而我们能否用可控成本持续交付客户认可的结果。**
> 
> 

---

# GEO商业验证实验 V2\.0

## 一、实验总目标

验证下面 5 个核心命题：

最终不是得到一个“成功/失败”的结论，而是得到：

> **继续 / 调整 / 暂停 / 换市场 / 换产品 / 换交付模式**
> 
> 

之一。

---

# 二、实验设计总图

整个实验分成四层。

```Plain Text
GEO商业验证 V2.0
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
     客户验证            结果验证           交付验证
        │                  │                  │
   问题/付费/续费       Visibility          Cost-to-Serve
        │               Citation             Expert Time
        │               Referral             Exception
        │               Lead
        │
        └──────────────────┬──────────────────┘
                           │
                       渠道验证
                           │
                  Partner-led Revenue
                  Partner Independence
```

注意：

**渠道实验放在最后。**

因为如果客户本身都不愿意买，先验证渠道没有意义。

---

# 三、第一阶段：客户招募实验

## 3\.1 不再简单规定“找 5–10 个客户”

这一次我们采用：

> **样本 × 来源 × 类型 × 价格 × 阶段**
> 
> 

五维记录。

### 客户来源必须记录

每一个客户必须标记：

- Founder Network

- Cold Outbound

- Inbound

- Referral

- Community

- Partner

- Existing Relationship

为什么？

因为：

> “我的朋友愿意买” ≠ “市场愿意买”。
> 
> 

---

# 四、客户分组

第一批建议：

### 目标：12 个真实商业客户

不是要求一定拿到 12 个。

而是**最多尝试招募 12 个**。

建议结构：

但这只是**实验结构**，不是最终 ICP。

实验过程中允许发现：

> “原来只有 B2B SaaS 真正愿意持续购买。”
> 
> 

那么这就是非常有价值的实验结果。

---

# 五、第二个重大改变：Research Customer ≠ Commercial Customer

这一点非常重要。

以后所有客户必须标记：

### A\. Research Customer

可以低价、甚至特殊条件进入。

目的：

> 学习产品。
> 
> 

### B\. Commercial Customer

按照正式商业价格购买。

目的：

> 验证商业模式。
> 
> 

不能把 A 当成 B。

否则很容易出现：

> “10个客户全部愿意做。”
> 
> 

但实际上其中 8 个是因为你给了巨大折扣、熟人关系或者大量人工服务。

这不能证明商业模式。

---

# 六、价格实验

第一轮不急着确定最终价格。

而是测试三个价格带。

例如：

**注意：这些仍然只是实验价格，不是最终定价。**

每组尽量安排相似类型客户。

例如：

```Plain Text
B2B SaaS
 ├── $499
 ├── $799
 └── $1,199
```

而不是：

```Plain Text
低质量客户 → $499
优质客户 → $1,199
```

否则无法判断价格因素。

---

# 七、客户真正购买什么，要单独验证

不能默认客户买的是：

> GEO
> 
> 

我们需要验证客户实际上愿意为哪一个东西付钱。

每个客户都要记录：

### 购买动机

A\. AI Visibility Monitoring

B\. AI Citation / Mention

C\. GEO Diagnosis

D\. GEO Strategy

E\. Content Optimization

F\. AI Referral / Traffic

G\. AI Lead Generation

H\. Competitor Intelligence

I\. Managed GEO Growth

最终我们要找到：

> **Customer Job\-to\-be\-Done**
> 
> 

也就是：

### “如果只能留下一个功能/服务，你最不愿意失去什么？”

这个问题的答案，可能直接决定最终产品形态。

---

# 八、第三阶段：建立 Baseline Protocol

客户正式开始之前，必须建立基线。

否则后面所有“增长”都有可能是主观判断。

---

## Week 0

记录：

### Prompt Set

建立固定 Prompt。

分成：

**Core Prompts**

长期固定，不轻易改变。

例如：

```Plain Text
P01
P02
P03
...
P50
```

### Exploration Prompts

根据客户业务动态增加。

---

# 九、Prompt必须分层

例如：

```Plain Text
Brand
Category
Problem
Comparison
Alternative
Purchase Intent
Local
Decision Stage
```

不要只测：

> “What is XXX?”
> 
> 

因为这类问题商业价值可能很低。

真正重要的是：

> **客户是否进入 AI 用户的决策过程。**
> 
> 

---

# 十、加入 Holdout

这是 V2\.0 和之前版本最大的实验设计升级之一。

例如：

```Plain Text
100 prompts

80 → Optimization Set
20 → Holdout Set
```

80 个用于优化。

20 个在实验期间尽量不针对性优化。

目的不是创造严格科学意义上的实验对照组——AI Search 环境无法做到真正随机对照。

而是观察：

> **优化区域与非优化区域是否出现不同的变化轨迹。**
> 
> 

因此最终只能说：

> Longitudinal evidence
> 
> 

而不能夸张成：

> GEO caused X% growth\.
> 
> 

---

# 十一、建立 GEO Intervention Log

这个东西以后甚至可能成为你整个 GEO 系统最有价值的数据资产之一。

每次做任何优化，都必须记录：

例如：

```Plain Text
I027

Target:
Product comparison page

Prompt Cluster:
Comparison / Purchase Intent

Action:
Added comparison section + structured product facts

Reason:
Competitor cited more frequently in decision-stage prompts

Expected:
Improve citation / inclusion

Status:
Completed
```

然后再观察：

```Plain Text
Intervention
      ↓
Time
      ↓
Visibility
      ↓
Citation
      ↓
Referral
      ↓
Lead
```

这样你开始拥有真正的：

> **GEO Intervention → Outcome Dataset**
> 
> 

这比单纯做一个 GEO Score 有价值很多。

---

# 十二、建立 Evidence Ladder

不要要求每个客户都做到 Revenue。

我们采用六级证据。

例如：

```Plain Text
客户A

L1 PASS
L2 PASS
L3 PASS
L4 UNKNOWN
L5 UNKNOWN
```

这不是失败。

因为 GEO → Revenue 本身存在很长的归因链。

---

# 十三、真正需要观察的六个核心指标

我建议把 V2\.0 的核心 Dashboard 压缩成这六个。

## ① Willingness to Pay

客户到底愿不愿意付钱。

---

## ② Visibility / Citation Change

有没有发生可观察变化。

---

## ③ Intervention → Outcome

做了什么之后，发生了什么变化。

---

## ④ Expert Minutes / Customer

每个客户到底消耗多少专家时间。

这个指标极其重要。

因为：

> $1,000/月收入
> 如果需要你人工投入 20 小时
> 可能根本不是好生意。
> 
> 

---

## ⑤ Renewal at Standard Price

不是：

> “客户满意。”
> 
> 

而是：

> **客户愿不愿意继续按照正常商业价格付钱。**
> 
> 

这是商业验证的核心指标之一。

---

## ⑥ Partner\-led Revenue

最终渠道能不能真正带来收入。

不是：

> Partner says “this is interesting\.”
> 
> 

而是：

> Partner 找到客户 → Partner 销售 → 客户付款。
> 
> 

---

# 十四、客户实验周期不要再简单定义成“90天”

90天可以作为一个观察窗口。

但不要把它写成：

> GEO必须90天见效。
> 
> 

我们改成：

### Evidence Windows

```Plain Text
W0
Baseline

W2
Early Signal

W4
First Evaluation

W8
Midpoint

W12
Commercial Review
```

这样更加科学。

---

# 十五、每个时间节点看什么？

### W0

回答：

> 我们测到了什么？
> 
> 

---

### W2

回答：

> 数据稳定吗？
> 
> 

以及：

> 有没有早期变化？
> 
> 

---

### W4

回答：

> 干预是否开始产生信号？
> 
> 

---

### W8

回答：

> 是否形成持续变化？
> 
> 

---

### W12

回答：

> 客户愿不愿意继续付钱？
> 
> 

---

# 十六、客户访谈必须加入

不能只看后台数据。

W4 和 W12 都做访谈。

重点问：

### Q1

“你现在是否认为 AI Search Visibility 是一个值得持续投入的问题？”

### Q2

“如果我们停止服务，你最担心失去什么？”

### Q3

“我们提供的哪些东西对你最有价值？”

### Q4

“如果只能保留一个功能，你会留下什么？”

### Q5

“你认为我们目前的价格是否合理？”

### Q6

“如果价格提高 30%，你会继续吗？”

### Q7

“如果停止 GEO，你会自己做、找人做，还是完全不做？”

最后一个问题尤其重要。

因为它告诉我们：

> **GEO究竟在替代什么。**
> 
> 

---

# 十七、必须测试 Counterfactual

我们不能只问：

> “优化之后有没有增长？”
> 
> 

还必须问：

> **“如果什么都不做，会怎样？”**
> 
> 

可使用：

### 方法1

Holdout prompts

### 方法2

Historical baseline

### 方法3

Competitor baseline

### 方法4

未优化页面

### 方法5

同期其他渠道变化

最终形成：

```Plain Text
Observed Change
        ↓
Possible Causes
        ↓
Intervention Evidence
        ↓
Counterfactual Evidence
        ↓
Confidence Level
```

---

# 十八、交付成本实验

这是很多 GEO 公司最容易忽略的地方。

每个客户必须记录：

```Plain Text
AI API Cost
+
Infrastructure Cost
+
Browser / Collector Cost
+
Expert Time
+
Customer Support
+
Account Management
+
Exception Handling
```

最终得到：

### Cost\-to\-Serve / Customer / Month

---

# 十九、加入 Exception Rate

以后真正决定你能不能规模化的，很可能不是平均成本。

而是：

> **异常率。**
> 
> 

例如：

100个客户：

```Plain Text
80个自动运行
15个需要人工调整
5个出现重大异常
```

那么：

> Exception Rate = 20%
> 
> 

如果：

```Plain Text
Exception Rate = 50%
```

你就不是 SaaS\-like delivery。

你其实是在经营：

> AI \+ 人工服务外包。
> 
> 

这对商业模式影响巨大。

---

# 二十、最终客户 PASS 标准

这里我要特别强调：

**不要使用“5个客户、3个续费”这种简单标准作为唯一 PASS。**

建议采用多维判断。

### PASS

必须同时看到：

```Plain Text
商业需求
+
真实付费
+
可观察结果
+
可接受交付成本
+
持续付费意愿
```

---

## Strong PASS

如果出现：

```Plain Text
陌生客户主动购买
+
标准价格
+
结果改善
+
客户愿意续费
+
专家时间下降
+
客户愿意推荐
```

这才是真正强信号。

---

# 二十一、FAIL也要定义

### FAIL A：没人愿意付钱

可能：

> Problem / Positioning Fail
> 
> 

---

### FAIL B：愿意付钱，但看不到结果

可能：

> Product / Methodology Fail
> 
> 

---

### FAIL C：结果不错，但成本太高

可能：

> Delivery Model Fail
> 
> 

---

### FAIL D：客户满意，但不续费

可能：

> Recurring Value Fail
> 
> 

---

### FAIL E：客户续费，但只能靠创始人销售

可能：

> Channel Scalability Fail
> 
> 

---

# 二十二、渠道实验放到第二阶段

等至少有一批真实客户以后，再测试 Partner。

目标：

### 5个 Partner

但同样不以“签约”作为成功标准。

---

# 二十三、Partner Independence 四级

### Level 1

Founder参与销售。

> ❌ 不算渠道验证。
> 
> 

### Level 2

Partner负责主要销售，Founder辅助。

> ⚠️ 初步信号。
> 
> 

### Level 3

Partner能够独立完成销售并成交。

> ✅ 有效渠道信号。
> 
> 

### Level 4

Partner可以持续自主获客、销售、成交。

> 🟢 真正的渠道规模化信号。
> 
> 

最终我们真正想要的是：

> **Level 3 → Level 4**
> 
> 

---

# 二十四、还必须问 Partner 一个关键问题

直接问：

> **“如果没有我们的 GEO 系统，你会怎么解决这个客户的问题？”**
> 
> 

答案可能是：

```Plain Text
A. 自己开发
B. 招 GEO 人员
C. 买其他工具
D. 外包
E. 不解决
```

这个问题非常重要。

因为它决定：

> **你到底在替渠道创造什么价值。**
> 
> 

如果答案全部是：

> “客户根本不会做。”
> 
> 

那你的产品价值可能只是教育市场。

如果答案是：

> “他们需要 GEO，但自己做太贵，我们需要一个后端。”
> 
> 

这才是真正强的 Partner Value Proposition。

---

# 二十五、Partner经济模型不要只看毛利

以前我们讨论过：

> Partner 30%毛利。
> 
> 

这还不够。

真正应该计算：

```Plain Text
Partner Contribution
=
Gross Margin
-
Sales Cost
-
Support Cost
-
Account Management
-
CAC Amortization
```

例如：

```Plain Text
客户售价 $1,000

Partner收入 $300

但：

Sales Cost       $100
Support           $50
Account Mgmt      $50
CAC Amortization  $30

Partner Contribution = $70
```

那么所谓“30%毛利”其实并不漂亮。

---

# 二十六、整个 V2\.0 最终形成一个决策树

```Plain Text
开始
                   │
                   ▼
            客户愿意付费？
             /          \
           NO            YES
           │              │
       改定位/市场       有结果？
                          /   \
                        NO     YES
                        │        │
                   改产品/方法   成本可控？
                                  /    \
                                NO      YES
                                │         │
                          改交付模型     客户续费？
                                           / \
                                         NO   YES
                                         │     │
                                   改产品价值   渠道实验
                                                  │
                                           Partner能独立成交？
                                               /       \
                                             NO         YES
                                             │            │
                                         渠道不成立      SCALE
```

---

# 二十七、我建议你现在不要急着做产品定价

这是这轮审计后，我认为最重要的战略调整。

我们之前已经讨论了：

> GEO Visibility
> GEO Growth
> GEO Managed Growth
> 
> 

以及：

> $299 / $699 / $1,499\+
> 
> 

但现在：

**暂时全部不要锁死。**

因为实验本身就是为了回答：

> **客户到底愿意买什么？**
> 
> 

有可能最后不是：

```Plain Text
Basic
Pro
Enterprise
```

而是：

```Plain Text
Measure
    ↓
Diagnose
    ↓
Grow
```

甚至可能发现：

```Plain Text
GEO Monitoring
```

客户根本不愿意单独付钱，

但：

```Plain Text
GEO Managed Growth
```

客户愿意付 $1,500/月。

那么我们的产品设计就应该服从实验结果。

---

# 二十八、V2\.0真正的终点

最终我们不是要得到一份漂亮的商业计划书。

而是得到下面这一张表：

当这些问号逐渐变成真实数据之后：

> **Product \& Pricing V1\.0 才有资格正式定稿。**
> 
> 

---

## 最后，我给这套 V2\.0 一个明确定位

它已经不应该叫：

> “GEO商业模式方案”
> 
> 

而应该叫：

> **GEO Business Validation System｜GEO商业验证系统**
> 
> 

因为它本质上已经开始成为你未来整个 GEO 业务的**商业实验操作系统**：

```Plain Text
客户
 ↓
Prompt
 ↓
Baseline
 ↓
Intervention
 ↓
Measurement
 ↓
Outcome
 ↓
Cost
 ↓
Renewal
 ↓
Partner
 ↓
Scale
```

而且这和你现在正在开发的 **GEO AI Visibility Measurement \& Diagnostic System** 是可以逐渐接起来的：

```Plain Text
技术系统
GEO Measurement
      ↓
业务系统
GEO Business Validation
      ↓
商业系统
GEO Platform + Channel + Centralized Fulfillment
```

这三层一旦打通，你现在做的就不再只是一个“GEO工具”，而是在逐渐形成一套**可验证、可交付、可复制的 GEO 商业基础设施**。





