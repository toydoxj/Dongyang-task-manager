"use client";

/**
 * 사용 매뉴얼 페이지 — 전 사용자 접근 가능.
 * 콘텐츠 출처: docs/USER_MANUAL.md (관리자가 변경하면 이 파일도 동기 갱신).
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
        <H3>3.1 대시보드 (관리자 / 팀장 / 관리팀)</H3>
        <Ul>
          <li>월별 추이 차트: 수주액·수금액·지출액 막대 + 12개월 선형회귀 추세선</li>
          <li>
            진행단계 칸반 (7개 컬럼) — 카드 드래그로 단계 변경(<B>관리자만</B>).
            완료/타절/종결로 옮기면 완료일·금액 입력 모달 자동 호출. 우측 끝
            <B>[+ 새 프로젝트]</B> 컬럼에서 즉석 등록(담당자 비어있는 상태,
            진행단계 = <code>대기</code>)
          </li>
          <li>팀별/직원별 부하 히트맵, 업무유형 매출 트리맵, 현금흐름 예측</li>
          <li>일반 직원은 대시보드 진입 시 「내 업무」로 자동 이동</li>
        </Ul>

        <H3>3.2 프로젝트 목록</H3>
        <P>검색 / 단계 / 팀 / 완료 여부 필터. 카드 클릭 → 프로젝트 상세.</P>

        <H3>3.3 프로젝트 상세 (위→아래)</H3>
        <Ol>
          <li>
            <B>헤더</B> — 프로젝트명 옆 <B>「편집」</B> /{" "}
            <B>「🔖 날인요청」</B> 버튼. 우측에 단계변경/진행단계
          </li>
          <li>
            <B>라이프사이클 타임라인</B> — 수주 → 계약기간 → 완료 + 마일스톤
          </li>
          <li>
            <B>담당 이력 swim lane</B> — 담당자별 지정~해제 기간을 색 막대로,
            진행 중은 끝에 →
          </li>
          <li>
            <B>날인 현황 리스트</B> — 이 프로젝트의 모든 날인요청. 항목 클릭 시
            상세 + 재날인요청 가능
          </li>
          <li>
            <B>업무 TASK 칸반</B> — 시작 전 / 진행 중 / 완료 / 보류, 드래그로
            상태 변경
          </li>
          <li>현금흐름 / 지출 구분 도넛 등</li>
        </Ol>
        <P>
          WORKS Drive 연결 시 <B>「폴더 보기」</B> / <B>「WORKS Drive」</B> /{" "}
          <B>「PC 경로 복사」</B>
        </P>

        <H3>3.4 내 업무 (/me)</H3>
        <Ul>
          <li>
            「해야할 일」 / 「담당 프로젝트」 / <B>「내 영업」</B> 세 섹션 모두{" "}
            <B>펼치기/접기</B> 가능
          </li>
          <li>
            <B>담당 프로젝트</B>는 진행 중 / 대기로 분리. 각 row 클릭 시 그
            프로젝트의 TASK 칸반이 펼쳐짐
          </li>
          <li>
            <B>내 영업</B>도 동일 row 스타일 — 수주영업/기술지원으로 묶임. row
            펼침 시 그 영업의 TASK 칸반 (영업 견적서 작성 task 자동 생성)
          </li>
          <li>
            「해야할 일」의 일정 카드(외근/출장/휴가) 중 <B>휴가 카드 우상단</B>
            에 <B>「+ 새 휴가」</B> 버튼 — 휴가(연차) 분류로 prefilled된 신규
            TASK 모달이 열림
          </li>
          <li>
            <B>「+ 새 프로젝트」</B> / <B>「프로젝트 가져오기」</B>
          </li>
          <li>
            <B>완료된 TASK는 저저번 주 월요일 이후</B> 완료된 것까지만 표시 —
            오래된 완료는 자동 정리
          </li>
          <li>
            우상단 <B>「주간업무일지 보기」</B> 버튼 — 주간업무일지 페이지로 진입
          </li>
        </Ul>

        <H3>3.5 날인요청 목록 페이지</H3>
        <Ul>
          <li>팀장/관리자 전용. 일반 직원은 프로젝트 상세에서 진행상황만</li>
          <li>
            정렬:
            <Ul>
              <li>팀장: 1차검토 중 → 2차검토 중 → 반려 → 승인</li>
              <li>관리자: 2차검토 중 → 1차검토 중 → 반려 → 승인</li>
              <li>같은 상태 안: 검토중·반려는 가까운 제출예정일 먼저, 승인은 최신순</li>
            </Ul>
          </li>
          <li>팀장은 본인 팀 직원 요청만 보임</li>
          <li>
            <B>팀장은 1차 단계에서만 처리(승인·반려) 가능</B>, 2차는 관리자
          </li>
        </Ul>

        <H3>3.6 주간업무일지 (/weekly-report)</H3>
        <Ul>
          <li>
            진입: <B>대시보드 우상단</B> 또는 <B>「내 업무」 우상단</B>의 emerald{" "}
            <B>「주간업무일지 보기」</B> 버튼 (사이드바엔 없음)
          </li>
          <li>
            상단 3개 날짜 입력 — 지난주 시작일 / 이번주 시작일(월요일 자동
            정규화) / 이번주 종료일. 마지막 발행분 기준으로 지난주 시작일이 자동
            셋팅됨
          </li>
          <li>
            <B>인원현황</B> · <B>공지/교육/건의</B> · <B>완료 프로젝트</B>(상태
            / CODE / 프로젝트명 / 발주처 / 담당팀 / 소요기간) ·{" "}
            <B>날인대장</B>(저번주 승인분, 승인일순) · <B>영업</B>(수주확률 포함)
            · <B>신규 프로젝트</B> · <B>개인 주간 일정</B>(5팀 grid + 본부) ·{" "}
            <B>팀별 업무 현황</B>(직원 셀병합 + 그룹 boundary) ·{" "}
            <B>대기/보류 프로젝트</B>(자체 2-col)
          </li>
          <li>
            <B>「PDF 확인」</B> (admin) — 현재 입력 기간으로 PDF 빌드 후 미리보기
          </li>
          <li>
            <B>「PDF 다운로드」</B> (비admin) — 가장 최근 <B>발행된</B> 일지만
            다운로드. 발행 이력 없으면 404
          </li>
          <li>
            <B>「발행」</B> (admin) — 확인 dialog 후 WORKS Drive{" "}
            <Code>[주간업무일지]/YYYYMMDD_주간업무일지.pdf</Code> 업로드 +{" "}
            <B>전 직원에게 Bot 알림 발송</B> (&quot;MMDD~MMDD 주간업무일지가 업로드
            되었습니다.&quot;) + 발행 로그 기록 (다음 일지 default 셋팅 기준)
          </li>
          <li>
            프로젝트명 / 영업명 등의 link는 <B>관리자만</B> 활성화 — 일반
            사용자에게는 plain text
          </li>
        </Ul>
      </Section>

      <Section title="4. 날인요청 자세히">
        <H3>4.1 등록 (프로젝트 상세 → 🔖 날인요청)</H3>
        <Ul>
          <li>검토구분: 구조계산서 / 구조안전확인서 / 구조검토서 / 구조도면 / 보고서 / 기타</li>
          <li>
            구조검토서는 <B>문서번호 자동 발급</B> (예:{" "}
            <Code>26-의견-057</Code>)
          </li>
          <li>
            검토자료 폴더 영역:
            <Ul>
              <li>
                미생성: <B>[📁 폴더 생성]</B> 클릭 →{" "}
                <Code>0.검토자료/오늘날짜/</Code> 자동 생성
              </li>
              <li>
                생성 후: <B>[📁 폴더 열기]</B> (임베디드 탐색기). 업로드/삭제 가능
              </li>
            </Ul>
          </li>
          <li>등록 시 폴더 없거나 비어있으면 confirm 경고</li>
          <li>첨부파일 input은 폐지 — Drive에 직접 업로드</li>
        </Ul>

        <H3>4.2 검토 흐름</H3>
        <Ol>
          <li>등록 → 자동 요청자 + 1차 검토자 TASK 생성, 1차 검토자에게 Bot 알림</li>
          <li>1차 승인 → 2차검토 중, 2차 검토자 TASK 생성, 관리자 전원에게 알림</li>
          <li>2차 승인 → 모든 TASK 완료(end=승인일), 요청자에게 알림</li>
          <li>반려 → 현재 단계 검토자 TASK 완료. 요청자에게 사유와 함께 알림</li>
          <li>재요청 — 반려된 항목 → 입력 수정 → 다시 1차검토 중</li>
        </Ol>

        <H3>4.3 재날인요청</H3>
        <P>
          프로젝트 상세 → 날인 현황 항목 클릭 → 상세 모달 →{" "}
          <B>[🔁 재날인요청]</B>
        </P>
        <Ul>
          <li>이전 입력 prefill (구조검토서는 같은 문서번호 유지)</li>
          <li>
            DB row 새로 만들지 않고 <B>같은 페이지에 덮어쓰기</B> + 자동 TASK 새
            사이클
          </li>
          <li>라이프사이클 / 담당 이력 / 칸반이 즉시 갱신</li>
        </Ul>

        <H3>4.4 날인취소</H3>
        <Ul>
          <li>[날인취소] → confirm 후 실행</li>
          <li>노션 페이지 archive 또는 (구조검토서 중간 번호) [날인취소] prefix</li>
          <li>연결된 모든 TASK는 완료 상태로 자동 마감 (history 보존)</li>
        </Ul>
      </Section>

      <Section title="5. 자주 쓰는 작업">
        <H3>5.1 새 프로젝트 만들기</H3>
        <Ol>
          <li>
            진입점 두 가지 — 「내 업무」 → <B>「+ 새 프로젝트」</B> (담당자 =
            본인 default) / <B>대시보드 진행단계 칸반 우측 끝의 [+ 새 프로젝트]
            컬럼</B> (담당자 빈 상태)
          </li>
          <li>프로젝트명 / Sub CODE / 발주처 / 수주일 / 용역비·VAT 입력</li>
          <li>
            발주처가 자동완성에 없으면 <B>「발주처 DB에 추가」</B> 클릭 → 노션
            발주처 DB에 신규 등록
          </li>
          <li>
            담당자: 콤마/엔터로 추가. 담당팀은 입력 불필요 — 노션 자동 집계
          </li>
          <li>업무내용: 노션 옵션에서 다중 선택 (자유 입력 가능)</li>
          <li>
            <B>「생성」</B> — 신규 프로젝트의 진행단계는 <code>대기</code>로 시작
            (TASK 활동이 잡히면 <code>진행중</code>으로 자동 전환)
          </li>
        </Ol>

        <H3>5.2 업무 TASK 등록</H3>
        <Ol>
          <li>
            프로젝트 상세 → 칸반의 <B>「+ 추가」</B>
          </li>
          <li>제목 / 시작일 / 마감일 / 담당자 / 우선순위 / 활동 입력</li>
          <li>
            분류 = <Code>휴가(연차)</Code> 선택 시 시간 지정 가능 (반차/시간
            단위)
          </li>
          <li>
            <B>「등록」</B>
          </li>
        </Ol>

        <H3>5.3 프로젝트 단계 변경 (완료 처리)</H3>
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

      <Section title="6. NAVER WORKS Bot 알림">
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
            <Tr l="주간업무일지 발행" r="전 직원" />
          </tbody>
        </table>
      </Section>

      <Section title="7. 자주 묻는 질문">
        <Faq
          q="「내 업무」가 비어있어요"
          a="본인 이름이 노션 담당자 옵션과 일치하지 않을 가능성이 큽니다. 우상단 프로필에서 본인 이름을 노션과 정확히 같은 형태로 수정해주세요."
        />
        <Faq
          q="발주처를 입력했는데 노션에 안 들어갔어요"
          a="입력한 이름이 발주처 DB에 등록되어 있지 않으면 임시 텍스트 컬럼에 들어갑니다. 입력란 아래 「발주처 DB에 추가」 버튼을 눌러야 정식 relation으로 저장됩니다."
        />
        <Faq
          q="휴가가 미분류로 보여요"
          a="이전 버그로 분류 표기가 어긋난 경우입니다. 모달에서 분류를 '휴가(연차)'로 다시 저장하면 정상 영역(일정 카드)으로 이동합니다."
        />
        <Faq
          q="날인요청 등록 후 알림을 못 받았어요"
          a="받는 사람의 NAVER WORKS 계정이 시스템에 연결되지 않은 경우 발송이 skip됩니다. 관리자에게 본인 NAVER WORKS ID 등록을 요청하세요."
        />
        <Faq
          q="자동 생성된 TASK가 보이지 않아요"
          a="이전 schema mismatch 버그(2026-05-02 수정)입니다. 새로 등록하시면 즉시 칸반에 표시됩니다."
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

      <Section title="8. 권한 안내">
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
              r="본인 담당 프로젝트/업무·영업 관리, 날인요청 등록, 본인 항목 재날인요청, 주간업무일지 PDF 다운로드(최근 발행본)"
            />
            <Tr
              l="팀장 (team_lead)"
              r="+ 대시보드, 같은 팀 직원 업무 보기 (/admin/employee-work), 날인 1차 승인/반려"
            />
            <Tr
              l="관리팀 (manager)"
              r="대시보드, 직원 일정, 사용 매뉴얼, 프로젝트, 영업/발주처/수금/지출/계약서 관리. 일반 직원 작업 영역(내 업무·날인·건의 등)과 시스템 관리는 미노출"
            />
            <Tr
              l="관리자 (admin)"
              r="+ 모든 메뉴, 칸반 단계 변경, 사용자 승인, 날인 2차 승인/반려, Drive 연결 관리, 주간업무일지 발행"
            />
          </tbody>
        </table>
      </Section>

      <Section title="9. 사이드바 메뉴 구조">
        <P>역할에 따라 자동 노출/숨김. 관리자 그룹은 <B>펼침/접힘</B> 가능.</P>
        <H3>9.1 공통 (label 없음, 항상 노출)</H3>
        <Ul>
          <li>대시보드 — admin / team_lead / manager</li>
          <li>내 업무 — admin / team_lead / member</li>
          <li>직원 업무 — admin / team_lead</li>
          <li>직원 일정, 사용 매뉴얼 — 모두</li>
          <li>날인요청, 건의사항, 유틸 런처 — admin / team_lead / member</li>
        </Ul>
        <H3>9.2 운영 관리 (admin / manager) — 펼침/접힘</H3>
        <Ul>
          <li>프로젝트, 영업 관리, 발주처 관리, 수금 관리, 지출 관리, 계약서 관리</li>
          <li>지출/계약서는 추후 페이지 추가 예정 (현재 placeholder)</li>
        </Ul>
        <H3>9.3 시스템 관리 (admin only) — 펼침/접힘</H3>
        <Ul>
          <li>공지/교육 관리, 직원 관리, 사용자 관리, Drive 연결</li>
        </Ul>
      </Section>

      <Section title="10. 문의">
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
