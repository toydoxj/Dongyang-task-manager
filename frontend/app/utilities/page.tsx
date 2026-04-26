"use client";

interface UtilityItem {
  name: string;
  description: string;
  url: string;
  category: "MIDAS" | "문서" | "외부";
  emoji: string;
}

const ITEMS: UtilityItem[] = [
  {
    name: "MIDAS Civil NX",
    description: "교량/구조 해석",
    url: "https://midasit.com/civil",
    category: "MIDAS",
    emoji: "🏗️",
  },
  {
    name: "MIDAS Gen NX",
    description: "건축 구조 설계",
    url: "https://midasit.com/gen",
    category: "MIDAS",
    emoji: "🏛️",
  },
  {
    name: "노션 워크스페이스",
    description: "원본 데이터베이스",
    url: "https://www.notion.so/41895be5a9644284a5c7ec568f2f9b18",
    category: "문서",
    emoji: "📄",
  },
  {
    name: "Google Drive",
    description: "공유 자료실",
    url: "https://drive.google.com",
    category: "문서",
    emoji: "📁",
  },
  {
    name: "KDS 건축구조기준",
    description: "기준·법규 검색",
    url: "https://www.kcsc.re.kr/",
    category: "외부",
    emoji: "📐",
  },
  {
    name: "기상청 지진정보",
    description: "내진설계 참고",
    url: "https://www.weather.go.kr/w/eqk-vol/recent/eqk-domestic.do",
    category: "외부",
    emoji: "🌐",
  },
];

export default function UtilitiesPage() {
  const grouped = new Map<string, UtilityItem[]>();
  for (const it of ITEMS) {
    const list = grouped.get(it.category) ?? [];
    list.push(it);
    grouped.set(it.category, list);
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">유틸 런처</h1>
        <p className="mt-1 text-sm text-zinc-500">
          업무에 자주 쓰는 외부 도구 모음. (관리자가 수정 — 추후 노션 DB 연동)
        </p>
      </header>

      {[...grouped.entries()].map(([cat, items]) => (
        <section key={cat}>
          <h2 className="mb-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
            {cat}
          </h2>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
            {items.map((it) => (
              <a
                key={it.url}
                href={it.url}
                target="_blank"
                rel="noopener noreferrer"
                className="group flex items-start gap-3 rounded-xl border border-zinc-200 bg-white p-4 transition-colors hover:border-zinc-300 hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:border-zinc-700 dark:hover:bg-zinc-800"
              >
                <span className="text-2xl">{it.emoji}</span>
                <div className="min-w-0 flex-1">
                  <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                    {it.name}
                    <span className="ml-1 text-zinc-400 transition-transform group-hover:translate-x-0.5">
                      ↗
                    </span>
                  </h3>
                  <p className="text-xs text-zinc-500">{it.description}</p>
                </div>
              </a>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
