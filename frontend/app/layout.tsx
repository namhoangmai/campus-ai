import type { Metadata } from "next";
import "./globals.css";

// Generalized from v1's TU/e-specific title/description -- this app now serves the widget page
// for any onboarded tenant (app/widget/page.tsx), not one institution. See ARCHITECTURE.md §8.
export const metadata: Metadata = {
  title: "Campus-AI",
  description: "Embeddable document Q&A widget, multi-tenant per university.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
