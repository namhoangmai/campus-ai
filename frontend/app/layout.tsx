import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TU/e Admission Assistant",
  description: "Ask questions about TU/e admission, enrollment, visas, and housing.",
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
