"use client";

/**
 * 사용 매뉴얼 페이지 — 전 사용자 접근 가능.
 *
 * 콘텐츠 출처: docs/USER_MANUAL.md (관리자가 변경하면 이 파일도 동기 갱신).
 * 마크다운 라이브러리 미사용 — Tailwind/JSX 로 직접 렌더해 빌드 부담 0.
 */

export default function HelpPage() {
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">사용 매뉴얼</h1>
        <p className="mt-1 text-sm text-zinc-500">
          (주)동양구조 임직원용. 화면별 사용법과 자주 쓰는 작업 안내.
        </p>
      </header>

      <Section title="1. 접속">
        <P>
          브라우저(권장: Chrome / Edge 최신)에서{" "}
          <Code>https://task.dyce.kr</Code> 접속. 설치할 앱은 없습니다. 사내
          어디서든 인터넷만 되면 같은 화면을 사용할 수 있습니다.
        </P>
      </Section>

      <Section title="2. 첫 사용 (로그인)">
        <H3>2.1 NAVER WORKS 로그인 (권장)</H3>
        <P>
          로그인 화면에서 <B>「NAVER WORKS로 로그인」</B> 클릭 → 회사 NAVER
          WORKS 계정으로 인증 → 자동 가입.
        </P>
        <H3>2.2 가입 신청 (비-NAVER WORKS 계정)</H3>
        <P>
          별도 가입이 필요한 경우 로그인 화면에서 <B>「가입 신청」</B> 클릭 →
          이름/이메일 입력 → <B>관리자 승인 후</B> 로그인 가능합니다.
        </P>
        <Note>
          본인 이름은 노션 담당자 옵션과 정확히 일치해야 「내 업무」에 본인
          프로젝트가 표시됩니다. 다르면 우상단 프로필에서 수정.
        </Note>
      </Section>

      <Section title="3. 주요 화면">
        <H3>3.1 대시보드 (관리자 / 팀장)</H3>
        <Ul>
          <li>월별 추이 차트: 수주액·수금액·지출액 막대 + 12개월 선형회귀 추세선</li>
          <li>
            진행단계 칸반 (7개 컬럼) — 카드 드래그로 단계 변경(관리자만).
            완료/타절/종결로 옮기면 완료일·금액 입력 모달 자동 호출
          </li>
          <li>팀별/직원별 부하 히트맵, 업무유형 매출 트리맵, 현금흐름 예측</li>
          <li>일반 직원은 대시보드 진입 시 「내 업무」로 자동 이동</li>
        </Ul>

        <H3>3.2 프로젝트 목록</H3>
        <P>검색 / 단계 / 팀 / 완료 여부 필터. 카드 클릭 → 프로젝트 상세.</P>

        <H3>3.3 프로젝트 상세</H3>
        <Ul>
          <li>
            제목 옆 <B>「편집」</B> / <B>「🔖 날인요청」</B> 버튼
          </li>
          <li>라이프사이클 타임라인 (수주 → 계약기간 → 완료, 마일스톤 표시)</li>
          <li>진행률 게이지 (프로젝트 진척 + 수금률)</li>
          <li>현금흐름 (수금/지출 누적 + 용역비 목표선)</li>
          <li>업무 TASK 칸반 — 카드 드래그로 상태 변경</li>
          <li>
            WORKS Drive 연결 시 <B>「폴더 보기」</B> / <B>「WORKS Drive」</B> /{" "}
            <B>「PC 경로 복사」</B>
          </li>
        </Ul>

        <H3>3.4 내 업무 (/me)</H3>
        <P>본인 담당 프로젝트만 표시. 마감 임박 TASK D-day 정렬.</P>
        <Ul>
          <li>
            <B>「+ 새 프로젝트」</B> — 새 프로젝트 등록
          </li>
          <li>
            <B>「프로젝트 가져오기」</B> — 다른 프로젝트의 담당자로 본인 추가
          </li>
        </Ul>

        <H3>3.5 날인요청</H3>
        <Ul>
          <li>등록은 프로젝트 상세의 「🔖 날인요청」 버튼에서만 가능</li>
          <li>
            검토구분: 구조계산서 / 구조안전확인서 / 구조검토서 / 구조도면 /
            보고서 / 기타
          </li>
          <li>
            구조검토서는 <B>문서번호 자동 발급</B> (예:{" "}
            <Code>26-의견-057</Code>)
          </li>
          <li>
            등록 시 <B>검토자료 폴더</B> 자동 안내 — <B>「📁 폴더 생성」</B>{" "}
            클릭 시 NAVER WORKS Drive에 <Code>0.검토자료/오늘날짜/</Code>{" "}
            폴더 생성, 이후 <B>「📁 폴더 열기」</B>로 임베디드 탐색기 진입(파일
            업로드/삭제 가능)
          </li>
          <li>등록 시 폴더가 없거나 비어있으면 확인 알림이 나옴</li>
        </Ul>
      </Section>

      <Section title="4. 자주 쓰는 작업">
        <H3>4.1 새 프로젝트 만들기</H3>
        <Ol>
          <li>
            「내 업무」 → <B>「+ 새 프로젝트」</B>
          </li>
          <li>프로젝트명 / Sub CODE / 발주처 / 수주일 / 용역비·VAT 입력</li>
          <li>
            발주처가 자동완성에 없으면 <B>「발주처 DB에 추가」</B> 클릭 → 노션
            발주처 DB에 신규 등록
          </li>
          <li>담당자: 본인이 default. 추가 인원 입력 가능 (콤마/엔터)</li>
          <li>업무내용: 노션 옵션에서 다중 선택 (자유 입력 가능)</li>
          <li>
            <B>「생성」</B>
          </li>
        </Ol>

        <H3>4.2 업무 TASK 등록</H3>
        <Ol>
          <li>
            프로젝트 상세 → 칸반의 <B>「+ 추가」</B>
          </li>
          <li>제목 / 시작일 / 마감일 / 담당자 / 우선순위 / 활동 입력</li>
          <li>
            <B>「등록」</B>
          </li>
        </Ol>

        <H3>4.3 날인요청 등록 (구조검토서 예시)</H3>
        <Ol>
          <li>
            프로젝트 상세 → <B>「🔖 날인요청」</B>
          </li>
          <li>
            검토구분: <B>구조검토서</B> 선택 → 문서번호 자동 발급 표시
          </li>
          <li>제출 예정일 / 내용요약 입력</li>
          <li>
            <B>「📁 폴더 생성」</B> 클릭 → 잠시 후 <B>「폴더 열기」</B>로 변경
          </li>
          <li>
            <B>「폴더 열기」</B> → 임베디드 탐색기에서 파일 드래그 업로드
          </li>
          <li>
            <B>「등록」</B> → 팀장/관리자에게 NAVER WORKS Bot 알림 발송
          </li>
        </Ol>

        <H3>4.4 프로젝트 단계 변경 (완료 처리)</H3>
        <Ol>
          <li>
            프로젝트 상세 헤더의 <B>「단계변경」</B> 클릭
          </li>
          <li>
            <B>완료</B> 선택 → 완료일(default 오늘) 확인 → <B>「저장」</B>
            <Ul>
              <li>타절: 타절금액 + VAT 입력</li>
              <li>종결: 용역비/VAT가 자동 ₩0</li>
            </Ul>
          </li>
        </Ol>
      </Section>

      <Section title="5. NAVER WORKS Bot 알림">
        <P>
          날인요청 단계별 알림이 NAVER WORKS 메신저로 자동 전송됩니다.
        </P>
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr className="border-b border-zinc-300 dark:border-zinc-700">
              <Th>시점</Th>
              <Th>받는 사람</Th>
            </tr>
          </thead>
          <tbody>
            <Tr l="날인요청 등록 (일반 직원)" r="같은 팀의 팀장" />
            <Tr l="날인요청 등록 (팀장/관리자)" r="관리자 전원 (본인 포함)" />
            <Tr l="1차 승인" r="관리자 전원 (본인 포함)" />
            <Tr l="최종 승인" r="요청자" />
            <Tr l="반려" r="요청자 (사유 포함)" />
          </tbody>
        </table>
      </Section>

      <Section title="6. 자주 묻는 질문">
        <Faq
          q="「내 업무」가 비어있어요"
          a="본인 이름이 노션 담당자 옵션과 일치하지 않을 가능성이 큽니다. 우상단 프로필에서 본인 이름을 노션과 정확히 같은 형태로 수정해주세요."
        />
        <Faq
          q="발주처를 입력했는데 노션에 안 들어갔어요"
          a="입력한 이름이 발주처 DB에 등록되어 있지 않으면 임시 텍스트 컬럼에 들어갑니다. 입력란 아래 「발주처 DB에 추가」 버튼을 눌러야 정식 relation으로 저장됩니다."
        />
        <Faq
          q="날인요청 등록 후 알림을 못 받았어요"
          a="받는 사람의 NAVER WORKS 계정이 시스템에 연결되지 않은 경우 발송이 skip됩니다. 관리자에게 본인 NAVER WORKS ID 등록을 요청하세요."
        />
        <Faq
          q="프로젝트가 노션에는 있는데 화면에서는 안 보여요"
          a="시스템은 노션과 5분 주기로 동기화합니다. 잠시 후 새로고침해보시고, 그래도 안 보이면 관리자에게 동기화 강제 실행을 요청하세요."
        />
        <Faq
          q="화면이 멈추거나 502 에러가 나와요"
          a="강력 새로고침: Ctrl + Shift + R. 그래도 계속되면 1~2분 후 재시도. 안 풀리면 관리자에게 문의해주세요."
        />
      </Section>

      <Section title="7. 권한 안내">
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr className="border-b border-zinc-300 dark:border-zinc-700">
              <Th>역할</Th>
              <Th>가능한 작업</Th>
            </tr>
          </thead>
          <tbody>
            <Tr
              l="일반 직원 (member)"
              r="본인 담당 프로젝트/업무 관리, 날인요청 등록"
            />
            <Tr
              l="팀장 (team_lead)"
              r="+ 같은 팀 직원 프로젝트 보기, 날인 1차 승인"
            />
            <Tr
              l="관리자 (admin)"
              r="+ 대시보드, 칸반 단계 변경, 사용자 승인, 날인 최종 승인"
            />
          </tbody>
        </table>
      </Section>

      <Section title="8. 문의">
        <P>
          문제나 개선 요청은 사내 IT 담당자에게 문의하거나 GitHub Issues로
          남겨주세요:{" "}
          <a
            href="https://github.com/toydoxj/Dongyang-task-manager/issues"
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-600 hover:underline dark:text-blue-400"
          >
            github.com/toydoxj/Dongyang-task-manager/issues
          </a>
        </P>
      </Section>
    </div>
  );
}

// ── 작은 표현 컴포넌트 ──

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2 rounded-lg border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
      <h2 className="text-lg font-semibold">{title}</h2>
      <div className="space-y-2 text-sm leading-relaxed text-zinc-700 dark:text-zinc-300">
        {children}
      </div>
    </section>
  );
}

function H3({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="mt-3 text-sm font-semibold text-zinc-900 dark:text-zinc-100">
      {children}
    </h3>
  );
}

function P({ children }: { children: React.ReactNode }) {
  return <p>{children}</p>;
}

function Ul({ children }: { children: React.ReactNode }) {
  return <ul className="list-inside list-disc space-y-1 pl-2">{children}</ul>;
}

function Ol({ children }: { children: React.ReactNode }) {
  return (
    <ol className="list-inside list-decimal space-y-1 pl-2">{children}</ol>
  );
}

function B({ children }: { children: React.ReactNode }) {
  return <strong className="font-semibold">{children}</strong>;
}

function Code({ children }: { children: React.ReactNode }) {
  return (
    <code className="rounded bg-zinc-100 px-1 py-0.5 text-[0.85em] font-mono dark:bg-zinc-800">
      {children}
    </code>
  );
}

function Note({ children }: { children: React.ReactNode }) {
  return (
    <p className="rounded-md border border-amber-500/40 bg-amber-500/5 p-2 text-xs text-amber-700 dark:text-amber-300">
      {children}
    </p>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th className="px-2 py-1.5 text-left font-medium text-zinc-600 dark:text-zinc-400">
      {children}
    </th>
  );
}

function Tr({ l, r }: { l: string; r: string }) {
  return (
    <tr className="border-b border-zinc-100 dark:border-zinc-800">
      <td className="px-2 py-1.5 align-top">{l}</td>
      <td className="px-2 py-1.5 align-top">{r}</td>
    </tr>
  );
}

function Faq({ q, a }: { q: string; a: string }) {
  return (
    <details className="rounded-md border border-zinc-200 bg-zinc-50 p-2 text-sm dark:border-zinc-800 dark:bg-zinc-950">
      <summary className="cursor-pointer font-medium text-zinc-900 dark:text-zinc-100">
        Q. {q}
      </summary>
      <p className="mt-1.5 text-xs text-zinc-600 dark:text-zinc-400">{a}</p>
    </details>
  );
}
