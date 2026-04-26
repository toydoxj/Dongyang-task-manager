"use client";

import { useMemo, useRef, useState } from "react";

import { cn } from "@/lib/utils";

interface Props {
  label: string;
  /** 사용자가 현재 고른 값들 */
  value: string[];
  /** 자동완성 후보 (노션 multi_select 기존 옵션) */
  options: string[];
  onChange: (next: string[]) => void;
  full?: boolean;
  placeholder?: string;
}

/**
 * 자유 입력 + 자동완성 + chips 멀티셀렉트.
 * - 선택된 값은 chips로 표시 (× 클릭 제거)
 * - 입력란 타이핑 시 미선택 옵션을 dropdown 자동완성
 * - Enter: 자동완성 강조 항목 또는 입력값 그대로 추가 (기존에 없는 신규 옵션 OK)
 * - Backspace(빈 입력): 마지막 chip 제거
 * - 화살표 ↑/↓: dropdown 항목 이동
 */
export default function MultiSelectChips({
  label,
  value,
  options,
  onChange,
  full,
  placeholder,
}: Props) {
  const [text, setText] = useState("");
  const [active, setActive] = useState(0);
  const [open, setOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const suggestions = useMemo(() => {
    const q = text.trim().toLowerCase();
    const selected = new Set(value);
    return options.filter(
      (o) => !selected.has(o) && (q === "" || o.toLowerCase().includes(q)),
    );
  }, [text, options, value]);

  function add(raw: string) {
    const v = raw.trim();
    if (!v) return;
    if (value.includes(v)) return;
    onChange([...value, v]);
    setText("");
    setActive(0);
  }

  function removeAt(i: number) {
    onChange(value.filter((_, idx) => idx !== i));
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.preventDefault();
      const pick = suggestions[active] ?? text;
      add(pick);
    } else if (e.key === "Backspace" && text === "" && value.length > 0) {
      removeAt(value.length - 1);
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, Math.max(suggestions.length - 1, 0)));
      setOpen(true);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Escape") {
      setOpen(false);
    } else if (e.key === ",") {
      // 콤마 입력으로도 추가 — 기존 콤마 입력 습관 호환
      e.preventDefault();
      add(text);
    }
  }

  return (
    <label className={cn("block text-xs", full && "sm:col-span-2")}>
      <span className="text-zinc-500">{label}</span>
      <div className="relative mt-0.5">
        <div className="flex flex-wrap items-center gap-1 rounded border border-zinc-300 bg-white px-1.5 py-1 dark:border-zinc-700 dark:bg-zinc-900">
          {value.map((v, i) => (
            <span
              key={`${v}-${i}`}
              className="inline-flex items-center gap-1 rounded bg-zinc-200 px-1.5 py-0.5 text-[11px] text-zinc-800 dark:bg-zinc-700 dark:text-zinc-100"
            >
              {v}
              <button
                type="button"
                onClick={() => removeAt(i)}
                className="text-zinc-500 hover:text-red-500"
                aria-label={`${v} 제거`}
              >
                ×
              </button>
            </span>
          ))}
          <input
            ref={inputRef}
            type="text"
            value={text}
            placeholder={value.length === 0 ? (placeholder ?? "선택 또는 입력") : ""}
            onChange={(e) => {
              setText(e.target.value);
              setOpen(true);
              setActive(0);
            }}
            onFocus={() => setOpen(true)}
            onBlur={() => {
              // dropdown 클릭으로 add되도록 약간 지연
              setTimeout(() => setOpen(false), 150);
            }}
            onKeyDown={onKeyDown}
            className="min-w-[80px] flex-1 bg-transparent px-1 text-xs text-zinc-900 outline-none dark:text-zinc-100"
          />
        </div>
        {open && suggestions.length > 0 && (
          <ul className="absolute left-0 right-0 top-full z-10 mt-0.5 max-h-48 overflow-auto rounded border border-zinc-200 bg-white shadow-md dark:border-zinc-700 dark:bg-zinc-900">
            {suggestions.map((s, i) => (
              <li key={s}>
                <button
                  type="button"
                  // mouseDown으로 처리해야 input blur 전에 잡힘
                  onMouseDown={(e) => {
                    e.preventDefault();
                    add(s);
                    inputRef.current?.focus();
                  }}
                  onMouseEnter={() => setActive(i)}
                  className={cn(
                    "block w-full px-2 py-1 text-left text-xs",
                    i === active
                      ? "bg-blue-500/15 text-blue-600 dark:text-blue-400"
                      : "text-zinc-800 hover:bg-zinc-100 dark:text-zinc-100 dark:hover:bg-zinc-800",
                  )}
                >
                  {s}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </label>
  );
}
