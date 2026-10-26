#!/usr/bin/env python3
"""Export the AIC application-effect survey as 问卷星 text-import format.

问卷星 has no public survey-creation API. Its "从文本创建问卷" dialog accepts a
plain-text question list; this script emits that list so the survey can be
created by paste instead of by hand.

Usage:
    python scripts/aic/wjx_survey_export.py
    python scripts/aic/wjx_survey_export.py --lang zh
    python scripts/aic/wjx_survey_export.py --lang en
    python scripts/aic/wjx_survey_export.py --lang bi --out tmp/wjx.txt
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path


SCALE = [
    ("1 非常不同意", "1 Strongly disagree"),
    ("2 不同意", "2 Disagree"),
    ("3 一般", "3 Neutral"),
    ("4 同意", "4 Agree"),
    ("5 非常同意", "5 Strongly agree"),
]


@dataclass
class Question:
    zh: str
    en: str
    kind: str = "single"  # single | multi | text
    options: list[tuple[str, str]] = field(default_factory=list)
    required: bool = True


@dataclass
class Section:
    zh: str
    en: str


def likert(zh: str, en: str) -> Question:
    return Question(zh, en, options=SCALE)


def single(zh: str, en: str, options: list[tuple[str, str]]) -> Question:
    return Question(zh, en, options=options)


def multi(zh: str, en: str, options: list[tuple[str, str]]) -> Question:
    return Question(zh, en, kind="multi", options=options)


def text(zh: str, en: str, required: bool = True) -> Question:
    return Question(zh, en, kind="text", required=required)


SURVEY: list[Section | Question] = [
    Section(
        "这份问卷约 5 分钟，匿名，不收集姓名、学校、院系和导师信息。目的是了解农业相关专业同学和老师在做气候—产量分析时的实际流程，以及一个演示系统是否能帮上忙。没有标准答案，请按真实感受作答；不想答的题可以直接跳过。",
        "This survey takes about 5 minutes and is anonymous. We do not collect your name, university, department, or advisor information. The purpose is to understand how students and faculty in agriculture-related fields analyze climate–yield relationships, and whether a demonstration system can help. There are no right or wrong answers; please respond based on your actual experience. You may skip any question you do not wish to answer.",
    ),
    Section("第一部分 基本信息", "Part 1: Background"),
    single(
        "你现在的身份是？",
        "What is your current role?",
        [
            ("本科生", "Undergraduate student"),
            ("硕士研究生", "Master's student"),
            ("博士研究生", "Doctoral student"),
            ("教师", "Faculty member"),
            ("科研助理", "Research assistant"),
            ("其他", "Other"),
        ],
    ),
    single(
        "你的专业或研究方向最接近？",
        "Which field is closest to your major or research area?",
        [
            ("作物学 / 农学", "Crop science / Agronomy"),
            ("农业气象", "Agricultural meteorology"),
            ("农业资源与环境", "Agricultural resources and environment"),
            ("农业经济管理", "Agricultural economics and management"),
            ("计算机 / 数据科学", "Computer science / Data science"),
            ("其他", "Other"),
        ],
    ),
    single(
        "你是否独立或参与做过“气候、极端天气与作物产量、粮食风险”相关的分析？",
        "Have you independently conducted, or participated in, analysis related to climate, extreme weather, crop yield, or grain risk?",
        [
            ("做过完整一次及以上", "Yes, at least one complete project"),
            ("参与过部分环节", "Participated in some steps"),
            ("只读过相关文献", "Only read related literature"),
            ("没做过", "No"),
        ],
    ),
    single(
        "最近一次这类任务，从拿到数据到做出可解释结果，大约用了多久？",
        "How long did your most recent such task take, from obtaining the data to producing an interpretable result?",
        [
            ("1 天以内", "Less than 1 day"),
            ("1–3 天", "1–3 days"),
            ("4–7 天", "4–7 days"),
            ("1–2 周", "1–2 weeks"),
            ("2 周以上", "More than 2 weeks"),
            ("没做过", "Have not done this"),
        ],
    ),
    multi(
        "你常用哪些工具？",
        "Which tools do you commonly use?",
        [
            ("Excel", "Excel"),
            ("SPSS", "SPSS"),
            ("R", "R"),
            ("Python", "Python"),
            ("ArcGIS 或 QGIS", "ArcGIS or QGIS"),
            ("Google Earth Engine", "Google Earth Engine"),
            ("现成脚本或模板", "Existing scripts or templates"),
            ("其他", "Other"),
        ],
    ),
    Section("第二部分 现在的分析流程", "Part 2: Current Workflow"),
    likert(
        "数据清洗和对齐（气象、遥感、统计年鉴等）占了我大部分时间。",
        "Data cleaning and alignment (meteorological, remote sensing, statistical yearbooks, etc.) take up most of my time.",
    ),
    likert(
        "不同数据源的指标口径不一致，我经常要反复确认。",
        "Indicators from different data sources are defined inconsistently, and I often have to verify them repeatedly.",
    ),
    likert(
        "换一个省或换一段时间做验证时，模型结果不稳定，我很难解释。",
        "When I validate the model in a different province or time period, the results are unstable and difficult to explain.",
    ),
    likert(
        "我很难向老师或审稿人说明模型为什么给出这个结果。",
        "It is difficult for me to explain to my advisor or reviewers why the model produced a given result.",
    ),
    likert(
        "现在的流程里，很多步骤只能靠手工记录，复现起来很麻烦。",
        "In my current workflow, many steps rely on manual records, making reproduction cumbersome.",
    ),
    Section("第三部分 试用任务", "Part 3: Trial Tasks"),
    single(
        "你是否完成了“找出某省某年主要风险因子”这个任务？",
        "Did you complete the task “identify the main risk factors for a province in a given year”?",
        [
            ("完成", "Completed"),
            ("部分完成", "Partially completed"),
            ("没完成", "Not completed"),
            ("没试用", "Did not try"),
        ],
    ),
    single(
        "你是否完成了“判断某县相对上一年的变化”这个任务？",
        "Did you complete the task “determine whether a county improved or worsened relative to the previous year”?",
        [
            ("完成", "Completed"),
            ("部分完成", "Partially completed"),
            ("没完成", "Not completed"),
            ("没试用", "Did not try"),
        ],
    ),
    single(
        "这两个任务你大约用了多久？",
        "Approximately how long did these two tasks take?",
        [
            ("3 分钟以内", "Under 3 minutes"),
            ("3–5 分钟", "3–5 minutes"),
            ("5–10 分钟", "5–10 minutes"),
            ("10 分钟以上", "More than 10 minutes"),
            ("没试用", "Did not try"),
        ],
    ),
    single(
        "过程中你需要别人提示或帮助吗？",
        "Did you need prompts or help from others during the tasks?",
        [
            ("完全不需要", "No help needed"),
            ("提示 1 次", "Prompted once"),
            ("提示多次", "Prompted multiple times"),
            ("没试用", "Did not try"),
        ],
    ),
    single(
        "关于“风险等级”和“产量”的关系，你的理解是？",
        "What is your understanding of the relationship between “risk level” and “yield”?",
        [
            ("风险等级高，产量一定低", "High risk level means yield must be low"),
            (
                "风险等级是气候条件的综合，不等于产量",
                "Risk level is a composite of climate conditions and is not equivalent to yield",
            ),
            ("风险等级和产量是同一个指标", "Risk level and yield are the same indicator"),
            ("不确定", "Not sure"),
        ],
    ),
    Section("第四部分 系统可用性（SUS）", "Part 4: System Usability (SUS)"),
    likert(
        "我愿意经常使用这个系统。",
        "I think that I would like to use this system frequently.",
    ),
    likert(
        "我觉得这个系统没有必要这么复杂。",
        "I found the system unnecessarily complex.",
    ),
    likert(
        "我觉得这个系统容易使用。",
        "I thought the system was easy to use.",
    ),
    likert(
        "我觉得我需要技术人员的帮助才能使用这个系统。",
        "I think that I would need the support of a technical person to be able to use this system.",
    ),
    likert(
        "我觉得这个系统的各项功能整合得很好。",
        "I found the various functions in this system were well integrated.",
    ),
    likert(
        "我觉得这个系统有很多不一致的地方。",
        "I thought there was too much inconsistency in this system.",
    ),
    likert(
        "我觉得大多数人能很快学会使用这个系统。",
        "I would imagine that most people would learn to use this system very quickly.",
    ),
    likert(
        "我觉得这个系统用起来很麻烦。",
        "I found the system very cumbersome to use.",
    ),
    likert(
        "我对使用这个系统很有信心。",
        "I felt very confident using the system.",
    ),
    likert(
        "我需要先学很多东西才能使用这个系统。",
        "I needed to learn a lot of things before I could get going with this system.",
    ),
    Section("第五部分 价值与使用意愿", "Part 5: Value and Intention to Use"),
    likert(
        "这个系统能帮我更快完成气候风险分析。",
        "This system can help me complete climate risk analysis faster.",
    ),
    likert(
        "这个系统给出的因子解释比我现在的做法更清楚。",
        "The factor explanations provided by this system are clearer than my current approach.",
    ),
    likert(
        "我相信系统给出的风险等级。",
        "I trust the risk levels shown by the system.",
    ),
    likert(
        "我相信系统给出的因子影响方向。",
        "I trust the direction of factor effects shown by the system.",
    ),
    likert(
        "我能在不求助他人的情况下看懂结果。",
        "I can understand the results without asking others for help.",
    ),
    likert(
        "如果下次做课程作业或科研，我愿意再用这个系统。",
        "I would be willing to use this system again for coursework or research.",
    ),
    likert(
        "我愿意把它推荐给同专业的同学或同事。",
        "I would recommend it to classmates or colleagues in my field.",
    ),
    Section("第六部分 开放题", "Part 6: Open Questions"),
    text(
        "刚才最让你困惑的一步是什么？如果没困惑，写“无”。（必答）",
        "What was the most confusing step just now? If nothing was confusing, write “None”. (Required)",
    ),
    text(
        "如果只能改一处，你先改哪里？（必答）",
        "If you could change only one thing, what would you change first? (Required)",
    ),
    text(
        "你觉得这个系统最适合谁用？（选填）",
        "Who do you think this system is most suitable for? (Optional)",
        required=False,
    ),
    Section("第七部分 匿名授权", "Part 7: Anonymous Use Consent"),
    single(
        "我同意将我的匿名回答和原话用于比赛材料与产品改进；不同意也不影响任何事。",
        "I agree that my anonymous responses and quotations may be used in competition submission materials and for product improvement. Your decision will not affect anything else.",
        [("同意", "Agree"), ("不同意", "Disagree")],
    ),
]


SHORT_SURVEY: list[Section | Question] = [
    Section(
        "这份问卷约 3 分钟，匿名，不收集姓名、学校、院系和导师信息。目的是了解你在做气候—产量分析时的实际流程，以及一个演示系统是否能帮上忙。没有标准答案，请按真实感受作答。",
        "This survey takes about 3 minutes and is anonymous. We do not collect your name, university, department, or advisor information. The purpose is to understand your actual workflow when analyzing climate–yield relationships, and whether a demonstration system can help. There are no right or wrong answers; please respond based on your actual experience.",
    ),
    Section("第一部分 基本信息", "Part 1: Background"),
    single(
        "你现在的身份是？",
        "What is your current role?",
        [
            ("本科生", "Undergraduate student"),
            ("硕士研究生", "Master's student"),
            ("博士研究生", "Doctoral student"),
            ("教师", "Faculty member"),
            ("科研助理", "Research assistant"),
            ("其他", "Other"),
        ],
    ),
    single(
        "你的专业或研究方向最接近？",
        "Which field is closest to your major or research area?",
        [
            ("作物学 / 农学", "Crop science / Agronomy"),
            ("农业气象", "Agricultural meteorology"),
            ("农业资源与环境", "Agricultural resources and environment"),
            ("农业经济管理", "Agricultural economics and management"),
            ("计算机 / 数据科学", "Computer science / Data science"),
            ("其他", "Other"),
        ],
    ),
    single(
        "你是否独立或参与做过“气候、极端天气与作物产量、粮食风险”相关的分析？",
        "Have you independently conducted, or participated in, analysis related to climate, extreme weather, crop yield, or grain risk?",
        [
            ("做过完整一次及以上", "Yes, at least one complete project"),
            ("参与过部分环节", "Participated in some steps"),
            ("只读过相关文献", "Only read related literature"),
            ("没做过", "No"),
        ],
    ),
    single(
        "最近一次这类任务，从拿到数据到做出可解释结果，大约用了多久？",
        "How long did your most recent such task take, from obtaining the data to producing an interpretable result?",
        [
            ("1 天以内", "Less than 1 day"),
            ("1–3 天", "1–3 days"),
            ("4–7 天", "4–7 days"),
            ("1–2 周", "1–2 weeks"),
            ("2 周以上", "More than 2 weeks"),
            ("没做过", "Have not done this"),
        ],
    ),
    Section("第二部分 现在的分析流程", "Part 2: Current Workflow"),
    likert(
        "数据清洗和对齐（气象、遥感、统计年鉴等）占了我大部分时间。",
        "Data cleaning and alignment (meteorological, remote sensing, statistical yearbooks, etc.) take up most of my time.",
    ),
    likert(
        "换一个省或换一段时间做验证时，模型结果不稳定，我很难解释。",
        "When I validate the model in a different province or time period, the results are unstable and difficult to explain.",
    ),
    Section("第三部分 试用任务", "Part 3: Trial Tasks"),
    single(
        "你是否完成了“找出某省某年主要风险因子”这个任务？",
        "Did you complete the task “identify the main risk factors for a province in a given year”?",
        [
            ("完成", "Completed"),
            ("部分完成", "Partially completed"),
            ("没完成", "Not completed"),
            ("没试用", "Did not try"),
        ],
    ),
    single(
        "你是否完成了“判断某县相对上一年的变化”这个任务？",
        "Did you complete the task “determine whether a county improved or worsened relative to the previous year”?",
        [
            ("完成", "Completed"),
            ("部分完成", "Partially completed"),
            ("没完成", "Not completed"),
            ("没试用", "Did not try"),
        ],
    ),
    single(
        "关于“风险等级”和“产量”的关系，你的理解是？",
        "What is your understanding of the relationship between “risk level” and “yield”?",
        [
            ("风险等级高，产量一定低", "High risk level means yield must be low"),
            (
                "风险等级是气候条件的综合，不等于产量",
                "Risk level is a composite of climate conditions and is not equivalent to yield",
            ),
            ("风险等级和产量是同一个指标", "Risk level and yield are the same indicator"),
            ("不确定", "Not sure"),
        ],
    ),
    Section("第四部分 使用感受", "Part 4: User Experience"),
    likert(
        "这个系统容易上手。",
        "This system is easy to get started with.",
    ),
    likert(
        "系统给出的结果我看得懂。",
        "I can understand the results shown by the system.",
    ),
    likert(
        "我相信系统展示的结果。",
        "I trust the results shown by the system.",
    ),
    likert(
        "下次课程作业或科研，我愿意再用这个系统。",
        "I would be willing to use this system again for coursework or research.",
    ),
    Section("第五部分 开放题与后续", "Part 5: Open Question and Follow-up"),
    text(
        "如果只能改一处，你先改哪里？为什么？",
        "If you could change only one thing, what would you change first, and why?",
    ),
    single(
        "是否愿意再花 10 分钟做一次带任务的深度试用？",
        "Would you be willing to spend another 10 minutes on a task-based trial?",
        [
            ("愿意", "Yes"),
            ("不愿意", "No"),
            ("看时间", "Depends on my schedule"),
        ],
    ),
    Section("第六部分 匿名授权", "Part 6: Anonymous Use Consent"),
    single(
        "我同意将我的匿名回答和原话用于比赛材料与产品改进；不同意也不影响任何事。",
        "I agree that my anonymous responses and quotations may be used in competition submission materials and for product improvement. Your decision will not affect anything else.",
        [("同意", "Agree"), ("不同意", "Disagree")],
    ),
]


def pick(zh: str, en: str, lang: str) -> str:
    if lang == "zh":
        return zh
    if lang == "en":
        return en
    return f"{zh} / {en}"


def render(survey: list[Section | Question], lang: str) -> str:
    lines: list[str] = []
    number = 0
    for item in survey:
        if isinstance(item, Section):
            lines.append(f"{pick(item.zh, item.en, lang)}[段落说明]")
            continue

        number += 1
        tag = ""
        if item.kind == "multi":
            tag = "[多选题]"
        lines.append(f"{number}、{pick(item.zh, item.en, lang)}{tag}")
        for index, (zh, en) in enumerate(item.options):
            letter = chr(ord("A") + index)
            lines.append(f"{letter}.{pick(zh, en, lang)}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def required_numbers(survey: list[Section | Question]) -> list[int]:
    numbers: list[int] = []
    number = 0
    for item in survey:
        if isinstance(item, Section):
            continue
        number += 1
        if item.required:
            numbers.append(number)
    return numbers


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lang", choices=["zh", "en", "bi"], default="bi")
    parser.add_argument(
        "--short",
        action="store_true",
        help="export the 16-question short version instead of the 36-question full version",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
    )
    args = parser.parse_args()

    survey = SHORT_SURVEY if args.short else SURVEY
    if args.out is None:
        lang_label = {"bi": "双语", "zh": "中文", "en": "英文"}[args.lang]
        prefix = "06_应用效果问卷_问卷星导入_精简" if args.short else "06_应用效果问卷_问卷星导入_"
        args.out = Path(f"docs/aic/{prefix}{lang_label}.txt")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(survey, args.lang), encoding="utf-8")

    total = sum(not isinstance(item, Section) for item in survey)
    print(f"wrote {args.out} ({total} questions, lang={args.lang})")
    print("required question numbers:", ",".join(map(str, required_numbers(survey))))
    print("optional question numbers:", ",".join(
        str(n) for n in range(1, total + 1) if n not in required_numbers(survey)
    ))


if __name__ == "__main__":
    main()
