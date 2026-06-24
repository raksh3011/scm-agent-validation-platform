import type { Metadata } from "next";
import "./globals.css";
import TopNav from "../components/TopNav";

export const metadata: Metadata = {
  title: "SCM Agent Validation Platform",
  description: "Deterministic-first trust validation for SCM AI agents",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <TopNav />
        {children}
      </body>
    </html>
  );
}
