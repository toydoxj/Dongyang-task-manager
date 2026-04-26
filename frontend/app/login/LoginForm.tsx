"use client";

import { useState } from "react";

import { login, register, requestJoin } from "@/lib/auth";

interface Props {
  isSetup: boolean;
  onSuccess: () => void;
}

type Mode = "login" | "setup" | "request";

const COMPANY_EMAIL_DOMAIN = "@dyce.kr";

export default function LoginForm({ isSetup, onSuccess }: Props) {
  const [mode, setMode] = useState<Mode>(isSetup ? "setup" : "login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent): Promise<void> => {
    e.preventDefault();
    setError("");
    setInfo("");

    // 가입/초기 설정 시 추가 검증
    if (mode !== "login") {
      if (password !== passwordConfirm) {
        setError("비밀번호가 일치하지 않습니다");
        return;
      }
      if (!email.toLowerCase().endsWith(COMPANY_EMAIL_DOMAIN)) {
        setError(`이메일은 회사 계정(${COMPANY_EMAIL_DOMAIN})만 사용 가능합니다`);
        return;
      }
    }

    setLoading(true);
    try {
      if (mode === "setup") {
        await register(username, password, name, email);
        onSuccess();
      } else if (mode === "login") {
        await login(username, password);
        onSuccess();
      } else {
        const r = await requestJoin(username, password, name, email);
        setInfo(r.message);
        setMode("login");
        setPassword("");
        setPasswordConfirm("");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "오류가 발생했습니다");
    } finally {
      setLoading(false);
    }
  };

  const showName = mode !== "login";
  const showEmail = mode !== "login";
  const showPasswordConfirm = mode !== "login";
  const title =
    mode === "setup"
      ? "초기 관리자 계정 생성"
      : mode === "request"
        ? "가입 신청"
        : "로그인";

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-950 px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <p className="text-xs font-medium uppercase tracking-wider text-zinc-500">
            (주)동양구조
          </p>
          <h1 className="mt-2 text-xl font-semibold text-white">업무관리 시스템</h1>
        </div>

        <form
          onSubmit={handleSubmit}
          className="space-y-4 rounded-xl border border-zinc-800 bg-zinc-900 p-6"
        >
          <h2 className="text-center text-sm font-semibold text-zinc-300">{title}</h2>

          {showName && (
            <Field label="이름" value={name} onChange={setName} placeholder="홍길동" required />
          )}
          {showEmail && (
            <Field
              label={`이메일 (${COMPANY_EMAIL_DOMAIN})`}
              type="email"
              value={email}
              onChange={setEmail}
              placeholder={`name${COMPANY_EMAIL_DOMAIN}`}
              required
            />
          )}
          <Field
            label="아이디"
            value={username}
            onChange={setUsername}
            placeholder="사용자 ID"
            required
            autoFocus
          />
          <Field
            label="비밀번호"
            type="password"
            value={password}
            onChange={setPassword}
            placeholder="비밀번호"
            required
          />
          {showPasswordConfirm && (
            <Field
              label="비밀번호 확인"
              type="password"
              value={passwordConfirm}
              onChange={setPasswordConfirm}
              placeholder="비밀번호 재입력"
              required
            />
          )}

          {error && <p className="text-center text-xs text-red-400">{error}</p>}
          {info && <p className="text-center text-xs text-emerald-400">{info}</p>}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-zinc-100 py-2.5 text-sm font-medium text-zinc-900 transition hover:bg-white disabled:opacity-50"
          >
            {loading ? "처리 중..." : title}
          </button>

          {mode === "login" && (
            <p className="text-center text-xs text-zinc-500">
              계정이 없으신가요?{" "}
              <button
                type="button"
                onClick={() => setMode("request")}
                className="text-zinc-300 underline-offset-2 hover:underline"
              >
                가입 신청
              </button>
            </p>
          )}
          {mode === "request" && (
            <p className="text-center text-xs text-zinc-500">
              이미 계정이 있으신가요?{" "}
              <button
                type="button"
                onClick={() => setMode("login")}
                className="text-zinc-300 underline-offset-2 hover:underline"
              >
                로그인
              </button>
            </p>
          )}
        </form>
      </div>
    </div>
  );
}

interface FieldProps {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  placeholder?: string;
  required?: boolean;
  autoFocus?: boolean;
}

function Field({
  label,
  value,
  onChange,
  type = "text",
  placeholder,
  required,
  autoFocus,
}: FieldProps) {
  return (
    <div>
      <label className="mb-1 block text-xs text-zinc-500">{label}</label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-white outline-none focus:border-zinc-500 focus:ring-2 focus:ring-zinc-700"
        placeholder={placeholder}
        required={required}
        autoFocus={autoFocus}
      />
    </div>
  );
}
