import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "GTM State & Signal Engine",
  description:
    "Strategy-aware, evidence-backed infrastructure for trustworthy descriptive GTM account state.",
  openGraph: {
    title: "GTM State & Signal Engine",
    description: "Know who matters, why now, and what to do next—with evidence.",
    type: "website",
  },
  twitter: {
    card: "summary",
    title: "GTM State & Signal Engine",
    description: "Know who matters, why now, and what to do next—with evidence.",
  },
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
