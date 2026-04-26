"use client";

import { ResponsiveTreeMap } from "@nivo/treemap";

import type { Project } from "@/lib/domain";
import { formatWon } from "@/lib/format";

interface Props {
  projects: Project[];
  title?: string;
  subtitle?: string;
}

interface TreeNode {
  name: string;
  value?: number;
  children?: TreeNode[];
}

function buildData(projects: Project[]): TreeNode {
  const buckets = new Map<string, number>();
  for (const p of projects) {
    const amount = p.contract_amount ?? 0;
    if (amount <= 0) continue;
    const types = p.work_types.length > 0 ? p.work_types : ["(미분류)"];
    // 다중 업무내용은 균등 분배 (대략적 추정)
    const share = amount / types.length;
    for (const t of types) {
      buckets.set(t, (buckets.get(t) ?? 0) + share);
    }
  }
  // 작은 항목은 "기타"로 묶기 (전체의 1% 미만)
  const total = [...buckets.values()].reduce((s, v) => s + v, 0);
  const threshold = total * 0.01;
  const main: TreeNode[] = [];
  let etcSum = 0;
  for (const [name, value] of buckets.entries()) {
    if (value < threshold) etcSum += value;
    else main.push({ name, value });
  }
  if (etcSum > 0) main.push({ name: "기타", value: etcSum });
  main.sort((a, b) => (b.value ?? 0) - (a.value ?? 0));
  return { name: "root", children: main };
}

export default function WorkTypeTreemap({
  projects,
  title = "업무유형 매출 분포",
  subtitle,
}: Props) {
  const data = buildData(projects);
  const total = (data.children ?? []).reduce((s, n) => s + (n.value ?? 0), 0);

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <header className="mb-3">
        <h3 className="text-sm font-semibold">{title}</h3>
        <p className="text-[10px] text-zinc-500">
          {subtitle
            ? `${subtitle} · `
            : ""}
          업무내용별 용역비 합 (다중 유형은 균등 배분, 1% 미만 = 기타) / 총{" "}
          {formatWon(total, true)}
        </p>
      </header>

      <div className="h-80">
        <ResponsiveTreeMap
          data={data}
          identity="name"
          value="value"
          valueFormat={(v) => formatWon(v, true)}
          margin={{ top: 5, right: 5, bottom: 5, left: 5 }}
          labelSkipSize={20}
          label={(node) => `${node.id}`}
          parentLabelTextColor={{ from: "color", modifiers: [["darker", 2]] }}
          colors={{ scheme: "set3" }}
          borderColor={{ from: "color", modifiers: [["darker", 0.3]] }}
          theme={{
            labels: {
              text: { fontSize: 11, fontWeight: 500 },
            },
            tooltip: {
              container: {
                background: "rgba(20,20,20,0.92)",
                color: "#e4e4e7",
                fontSize: 11,
              },
            },
          }}
        />
      </div>
    </div>
  );
}
