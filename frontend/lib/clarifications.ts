import { CalendarClock, GitBranch, Users, type LucideIcon } from "lucide-react";

export type ClarificationOption = {
  value: string;
  label: string;
  appendText?: string;
};

export type ClarificationQuestion = {
  id: string;
  icon: LucideIcon;
  question: string;
  options: ClarificationOption[];
};

export function buildClarificationQuestions(input: string, scenarioHint?: string): ClarificationQuestion[] {
  if (scenarioHint) return [];
  const text = input.trim();
  if (!text) return [];
  const questions: ClarificationQuestion[] = [];
  if (looksLikeGroupPlan(text) && !hasExplicitPartySize(text)) {
    questions.push({
      id: "party_size",
      icon: Users,
      question: "一共有几个人呀？",
      options: [
        { value: "4", label: "4人", appendText: "一共4人" },
        { value: "2", label: "2人", appendText: "一共2人" },
        { value: "3", label: "3人", appendText: "一共3人" },
        { value: "1", label: "1人", appendText: "一共1人" },
        { value: "5_plus", label: "更多", appendText: "一共5人以上" }
      ]
    });
  }
  if (looksLikeOpenPlan(text) && !hasConcreteSingleActivity(text) && !hasExplicitStopCount(text)) {
    questions.push({
      id: "stop_count",
      icon: GitBranch,
      question: "要安排几个活动呀？",
      options: [
        { value: "2", label: "2个", appendText: "安排2个活动" },
        { value: "3", label: "3个", appendText: "安排3个活动" },
        { value: "4", label: "4个", appendText: "安排4个活动" },
        { value: "auto", label: "你来定" }
      ]
    });
  }
  if (/周末|这周末|本周末/.test(text) && !/周六|周日|星期六|星期日|星期天|礼拜六|礼拜日|礼拜天/.test(text)) {
    questions.push({
      id: "weekend_day",
      icon: CalendarClock,
      question: "周末哪天更合适？",
      options: [
        { value: "sat", label: "周六", appendText: "周六出发" },
        { value: "sun", label: "周日", appendText: "周日出发" },
        { value: "auto", label: "你来定" }
      ]
    });
  }
  return questions.slice(0, 3);
}

export function enrichInputWithClarifications(input: string, answers: Record<string, string>, questions: ClarificationQuestion[]) {
  const additions = questions
    .map((question) => question.options.find((option) => option.value === answers[question.id])?.appendText)
    .filter((value): value is string => Boolean(value));
  if (!additions.length) return input;
  return `${input}。${additions.join("，")}。`;
}

function looksLikeGroupPlan(text: string) {
  return /朋友|同学|室友|同事|聚|多人|大家/.test(text) && !/女朋友|男朋友|对象|老婆|老公/.test(text);
}

function hasExplicitPartySize(text: string) {
  return /([1-9]\d?|[一二两三四五六七八九十])\s*(个)?人|一个人|自己|独自|女朋友|男朋友|对象|老婆孩子|孩子/.test(text);
}

function looksLikeOpenPlan(text: string) {
  return /安排|找个地方|出去玩|活动|地方|去玩|打游戏|电竞|桌游|KTV|唱歌|吃饭/.test(text);
}

function hasConcreteSingleActivity(text: string) {
  return /打游戏|电竞|网咖|网吧|KTV|唱歌|桌游|剧本杀|密室|电影|羽毛球|台球/.test(text) && !/然后|再|顺便|几个活动|多个活动/.test(text);
}

function hasExplicitStopCount(text: string) {
  return /([0-9一二两三四五六七八九十])\s*(?:-|~|到|至)?\s*([0-9一二两三四五六七八九十])?\s*(?:个)?(?:活动|地点|节点|项目|去处|地方|站)/.test(text);
}
