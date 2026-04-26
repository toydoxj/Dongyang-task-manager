import { ImageResponse } from "next/og";

// Apple Touch Icon — iOS 홈화면 추가 시 표시 (PNG 필수)
export const size = { width: 180, height: 180 };
export const contentType = "image/png";

export default function AppleIcon() {
  return new ImageResponse(
    (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          width: "100%",
          height: "100%",
          background: "white",
        }}
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 280 282"
          width="150"
          height="150"
        >
          <g transform="translate(0,282) scale(0.1,-0.1)" fill="#669900">
            <path d="M0 2405 l0 -415 707 0 708 1 278 -278 278 -277 -313 -313 -313 -313 -292 0 -293 0 0 525 0 525 -380 0 -380 0 0 -930 0 -930 878 0 877 0 523 523 522 522 0 888 0 887 -395 0 -395 0 0 -162 0 -163 -163 163 -162 162 -843 0 -842 0 0 -415z" />
            <path d="M2370 425 l-425 -425 428 0 427 0 0 425 c0 234 -1 425 -3 425 -1 0 -193 -191 -427 -425z" />
          </g>
        </svg>
      </div>
    ),
    size,
  );
}
