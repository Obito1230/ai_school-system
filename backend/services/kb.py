# -*- coding: utf-8 -*-
"""校园知识库（RAG 数据源）+ 轻量检索器。
纯 Python 实现的 TF 词频检索（无外部向量库依赖，Demo 可离线跑）：
- 语料：内置校园办事指引/求助渠道（生产可换成 MySQL/向量库，检索器接口不变）
- 检索：分词 → 词频倒排 → Top-K 召回 → 相似度归一化分数
RAG 链路：/ai/ask 接口 = 检索(recall) → 增强(augment 进 Prompt) → 生成(GLM) → 兜底(纯检索答案)。
"""
import math
import re
from collections import Counter

# ---------------- 知识库语料（title / content / tags） ----------------
KB_DOCS = [
    {"id": 1, "title": "校园卡挂失与补办",
     "content": "校园卡丢失后：① 登录信息门户「一卡通服务」自助挂失；② 携带身份证到卡务中心（行政楼一楼101室，工作日 8:30-17:00）补办，工本费 15 元；③ 补办后原卡余额 3 个工作日内自动转入新卡。",
     "tags": ["校园卡", "挂失", "补办", "卡务中心"]},
    {"id": 2, "title": "图书馆开放时间与借书规则",
     "content": "图书馆开放时间：周一至周五 8:00-22:00，周末 9:00-21:00（法定节假日另行通知）。本科生凭校园卡最多借 10 本，借期 30 天，可续借 1 次（15 天）；超期按 0.1 元/天收取滞纳金。借还书均可在自助借还机操作。",
     "tags": ["图书馆", "借书", "开放时间", "续借"]},
    {"id": 3, "title": "宿舍报修流程（水电/家具/网络）",
     "content": "宿舍设施报修走校内后勤服务中心官方渠道，不要找校外人员：① 线上：信息门户「后勤报修」提交工单（附照片）；② 电话：后勤服务中心 24 小时值班热线；③ 紧急情况（漏水/断电/安全隐患）直接拨打宿管值班电话。报修后 24 小时内响应。",
     "tags": ["宿舍", "报修", "维修", "后勤", "水电"]},
    {"id": 4, "title": "校园保卫处与紧急求助渠道",
     "content": "校园保卫处 24 小时值班电话（各校区见信息门户）。紧急情况（人身安全/财物被盗/可疑人员）第一时间联系保卫处或拨打110。夜间可请保卫处护送回宿舍（「平安护送」服务，21:00 后免费）。贵重物品遗失可到保卫处登记调取监控。",
     "tags": ["保卫处", "紧急", "安全", "护送", "被盗"]},
    {"id": 5, "title": "学业帮扶与答疑渠道",
     "content": "学业困难帮扶：① 各学院学业指导中心每周有高数/英语/专业课答疑（见学院通知）；② 图书馆学习支持中心有朋辈辅导预约；③ 本平台「学业答疑」类互助任务可发布辅导求助；④ 考试周教务处会组织集中答疑，关注教务在线。",
     "tags": ["学业", "答疑", "辅导", "高数", "帮扶"]},
    {"id": 6, "title": "勤工助学与代办跑腿规范",
     "content": "校内勤工助学岗位通过学生资助管理中心申请，时薪不低于当地最低标准。校外兼职警惕「刷单」「押金」类骗局。本平台代办跑腿任务仅限校园内、无现金交易（平台禁止现金往来，L3 拦截），取送物品请当面核验。",
     "tags": ["勤工助学", "跑腿", "代办", "兼职", "骗局"]},
    {"id": 7, "title": "心理健康支持渠道",
     "content": "大学生心理健康中心提供免费咨询（行政楼三楼，工作日预约），24 小时心理援助热线全国通用。遇到情绪困扰、学业压力、人际关系问题都可以预约咨询，信息严格保密。紧急心理危机请立即联系辅导员或保卫处。",
     "tags": ["心理", "咨询", "压力", "情绪", "援助"]},
    {"id": 8, "title": "校园互助平台使用规则",
     "content": "本平台工单流转：发布（AI 解析+风险分级）→ 广场展示 → 他人接单 → 完成 → 评价。信用积分：发布+2、接单+1、完成+5、好评额外加分，差评扣分，全部流水可追溯可申诉。禁止事项：现金交易（L3 拦截）、违规物品代购、考试作弊协助。L2 级工单需人工复核后展示。",
     "tags": ["互助平台", "规则", "信用", "积分", "拦截"]},
]

# ---------------- 轻量检索器（无外部依赖） ----------------
_STOP = set("的了和与及或是请在到被把从对向向着于关于按照根据通过作为以之为跟同给让去来上下里外中前后左右本该此这些那些什么怎么如何多少可以能否需要是否".split())


def _tokens(text: str) -> list[str]:
    """极简中文分词：2-gram + 短语 + 去停用词。Demo 场景召回足够；
    生产可替换 jieba/向量 embedding，recall() 接口不变。"""
    text = re.sub(r"[^\w\u4e00-\u9fff]+", " ", text.lower())
    words = [w for w in text.split() if len(w) > 1]
    grams = []
    for w in words:
        if len(w) <= 4:
            grams.append(w)
        # 长词切 2-gram（中文语素召回）
        grams += [w[i:i + 2] for i in range(len(w) - 1)] if re.search(r"[\u4e00-\u9fff]", w) else [w]
    return [t for t in grams if t not in _STOP and len(t) > 1]


def recall(query: str, k: int = 3) -> list[dict]:
    """TF 相似度 Top-K 召回。返回 [{id,title,content,tags,score}]，score∈(0,1]。"""
    q = Counter(_tokens(query))
    if not q:
        return []
    scored = []
    for doc in KB_DOCS:
        d = Counter(_tokens(doc["title"] + " " + doc["content"] + " " + " ".join(doc["tags"])))
        # 余弦相似度（词频向量点积 / 模长）
        dot = sum(c * d[t] for t, c in q.items() if t in d)
        if dot:
            score = dot / math.sqrt(sum(q.values()) * sum(d.values()))
            scored.append({**{k: doc[k] for k in ("id", "title", "content", "tags")}, "score": round(score, 3)})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:k]
