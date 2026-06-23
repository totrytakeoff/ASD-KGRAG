import { BookOpen, Database, GitBranch, FileText, Network, Layers, Eye, CheckCircle, BarChart3, Settings, AlertTriangle } from "lucide-react";

function BulletList({ items }: { items: string[] }) {
  return (
    <ul className="space-y-1 mt-1">
      {items.map((item, i) => (
        <li key={i} className="flex items-start gap-2 text-sm text-gray-600">
          <span className="mt-1 block h-1.5 w-1.5 shrink-0 rounded-full bg-medical-500" />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

interface Section {
  icon: React.ReactNode;
  title: string;
  intro: string;
  bullets?: string[][];
  code?: string[];
}

const sections: Section[] = [
  {
    icon: <Network size={18} />,
    title: "系统概述",
    intro: "ASD-KGRAG 是一个基于知识图谱的孤独症谱系障碍(ASD)领域检索增强生成问答系统。系统链路: 文献资料 -> 文档提取 -> 清洗 -> 分块 -> 实体关系抽取 -> 归一化 -> Neo4j 图谱 + Qdrant 向量库 -> 混合检索 -> KGRAG 问答 -> 评估。当前数据量: 3684 实体, 17816 关系, 7568 文献片段(Chunk)。",
  },
  {
    icon: <Layers size={18} />,
    title: "概览页面",
    intro: "图谱概览页面展示了整个知识图谱的宏观统计数据:",
    bullets: [
      ["实体/关系/Chunk 总数", "快速了解数据规模"],
      ["实体类型分布", "各类实体(评估工具、干预方法、症状等)的数量占比"],
      ["证据等级分布", "文献证据等级分布"],
      ["来源类型分布", "文献类型分布(article/narrative_review/systematic_review)"],
    ],
  },
  {
    icon: <Database size={18} />,
    title: "实体浏览",
    intro: "实体是知识图谱中的核心节点,每个实体代表 ASD 领域的某个概念。实体的类型包括:",
    bullets: [
      ["AssessmentTool", "评估/筛查工具(ADOS, M-CHAT, CARS 等)"],
      ["Intervention", "干预方法(ABA, ESDM, PRT 等)"],
      ["Symptom", "症状表现"],
      ["Condition", "疾病/诊断"],
      ["Comorbidity", "共病(ADHD, 焦虑, 睡眠问题等)"],
      ["Risk", "风险因素"],
      ["AgeStage", "年龄阶段"],
      ["Mechanism", "机制/原理"],
      ["Setting", "干预环境"],
      ["Task", "任务/活动"],
      ["Claim", "主张/结论"],
    ],
  },
  {
    icon: <GitBranch size={18} />,
    title: "关系浏览",
    intro: "关系连接两个实体,描述它们在 ASD 知识中的关联。重要字段包括:",
    bullets: [
      ["关系类型", "MEASURED_BY, TREATS, RISK_FOR, COMORBID_WITH 等"],
      ["support_count", "支持该关系的文献数(越高越可靠)"],
      ["confidence", "置信度(0-1 之间,越高越可靠)"],
      ["qa_usage", "问答使用策略(standard / use_with_caution / research_context_only / guardrailed_clinical_context)"],
    ],
  },
  {
    icon: <FileText size={18} />,
    title: "Chunk 浏览",
    intro: "Chunk 是从原始文献中切分的片段,每个 Chunk 对应一段连续的文本内容。字段含义:",
    bullets: [
      ["evidence_level", "证据等级(A/B/C/D)"],
      ["source_type", "来源类型(article, narrative_review, systematic_review_or_meta, trial)"],
      ["text_preview", "文本内容预览(可展开查看全文)"],
      ["doc_id", "来源文档 ID"],
    ],
  },
  {
    icon: <Eye size={18} />,
    title: "图谱可视化",
    intro: "力导向图展示了知识图谱的拓扑结构。",
    bullets: [
      ["操作方式", "拖拽移动节点, 滚轮缩放, 悬停查看详情"],
      ["节点大小", "关联度(连接数越多越大)"],
      ["节点颜色", "实体类型(见图例)"],
      ["线条粗细", "支持数(support_count)"],
    ],
  },
  {
    icon: <CheckCircle size={18} />,
    title: "评估题集管理",
    intro: "评估题集是 QA 评测的基础。支持手动录入和 CSV 批量导入:",
    bullets: [
      ["手动录入", "填写 ID、分类、问题内容、关键词, 勾选需要护栏"],
      ["CSV 批量导入", "支持 QAQUESTION / SAFETYQUESTION 格式, 自动校验表头, 去重合并"],
    ],
    code: ["格式: student_id,question_id,category,query,keywords,requires_guardrail,source_note,notes", "例: S01,Q001,assessment,ADOS 是什么？,ADOS;自闭症,true,文献综述,"],
  },
  {
    icon: <BarChart3 size={18} />,
    title: "评估运行",
    intro: "评估运行页面展示每次评测的详细结果。",
    bullets: [
      ["运行列表", "每次运行显示通过数/总数和通过率, 进度条展示整体质量"],
      ["运行详情", "全部/失败案例两种查看模式, 每题显示5项检查"],
      ["5 项检查", "上下文检索 / 图谱检索 / 预期术语匹配 / 答案引用 / 护栏声明"],
      ["失败案例", "可标记状态(待修复/已确认/已修复), 展开查看答案全文和检索上下文"],
    ],
  },
  {
    icon: <Settings size={18} />,
    title: "系统设置",
    intro: "系统设置包含问答模型和评估模型配置:",
    bullets: [
      ["当前问答模型", "模型名称、API 地址、API Key、超时、最大 Token、重试次数, 修改即时生效"],
      ["评估模型列表", "配置多个评估模型, 每个模型可独立设置 API 地址和 API Key, 支持启用/禁用和编辑"],
    ],
  },
  {
    icon: <AlertTriangle size={18} />,
    title: "别名管理",
    intro: "实体别名管理用于处理图谱中同一实体的不同名称。",
    bullets: [
      ["分组管理", "查看/编辑别名分组, 添加/删除别名, 搜索过滤, 新增分组"],
      ["候选审核", "学生提交的 ALIAS 结果进入待审核区, 可接纳为分组或忽略"],
    ],
  },
];

export default function DashboardGuide() {
  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <div>
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-medical-100 text-medical-700">
            <BookOpen size={20} />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-gray-900">使用说明</h1>
            <p className="text-sm text-gray-500">Dashboard 协作管理后台 · 模块说明与操作指南</p>
          </div>
        </div>
      </div>

      {sections.map((section, i) => (
        <div key={i} className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="mb-4 flex items-center gap-2">
            <span className="text-medical-600">{section.icon}</span>
            <h2 className="text-base font-semibold text-gray-900">{section.title}</h2>
          </div>
          <p className="text-sm leading-relaxed text-gray-600">{section.intro}</p>
          {section.bullets && (
            <div className="mt-3 space-y-2">
              {section.bullets.map((pair, j) => (
                <div key={j} className="flex items-start gap-2 text-sm">
                  <span className="mt-1.5 block h-1.5 w-1.5 shrink-0 rounded-full bg-medical-500" />
                  <div>
                    <span className="font-medium text-gray-700">{pair[0]}: </span>
                    <span className="text-gray-600">{pair[1]}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
          {section.code && (
            <div className="mt-3 rounded-lg bg-gray-50 p-3 font-mono text-xs text-gray-600">
              {section.code.map((line, j) => (
                <div key={j}>{line}</div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
