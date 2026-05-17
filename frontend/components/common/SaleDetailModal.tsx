"use client";

/**
 * PR-FS — 글로벌 영업 상세 모달.
 *
 * PR-FR(프로젝트)와 동일 패턴. SalesEditModal은 자체 modal UI를 이미 가지므로
 * 그대로 wrapping (별도 overlay layer 불필요). 다만 sale 객체가 prop으로
 * 필요하므로 store saleId → useSale(id) fetch 후 전달.
 *
 * /sales 페이지의 SalesEditModal과 동시 mount되지 않음:
 *   - /sales의 modal: clickedSale/queriedSale state 기반
 *   - 이 글로벌 modal: detailModal store saleId 기반
 * 다른 페이지(weekly-report, /me 등)에서 SalePopupLink 클릭 → 이 글로벌 modal만 표시.
 */

import { useEffect } from "react";

import SalesEditModal from "@/components/sales/SalesEditModal";
import { useSale } from "@/lib/hooks";
import { closeSaleModal, useSaleModalId } from "@/lib/stores/detailModal";

export default function SaleDetailModal() {
  const saleId = useSaleModalId();
  const { data: sale } = useSale(saleId);

  useEffect(() => {
    if (!saleId) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [saleId]);

  if (!saleId) return null;
  // sale fetch 중에는 가벼운 backdrop만 표시 — SalesEditModal에 null을 넘기면 신규 모드가 됨.
  if (!sale) {
    return (
      <div
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
        aria-busy="true"
      >
        <div className="rounded-md bg-white px-4 py-2 text-sm text-zinc-700 shadow dark:bg-zinc-900 dark:text-zinc-200">
          영업 정보 불러오는 중…
        </div>
      </div>
    );
  }
  return (
    <SalesEditModal
      key={sale.id}
      sale={sale}
      openNew={false}
      onClose={closeSaleModal}
    />
  );
}
