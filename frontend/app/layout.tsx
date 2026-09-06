import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Customer Intelligence",
  description: "근거 기반 고객 인텔리전스 Agent",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
