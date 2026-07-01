import type { Metadata } from "next";
import { Playfair_Display } from "next/font/google";
import "./globals.css";
import TopNav from "../components/TopNav";
import Providers from "../components/Providers";

const displayFont = Playfair_Display({
  subsets: ["latin"],
  variable: "--font-display",
  display: "swap",
});

export const metadata: Metadata = {
  title: "CirceAI — SCM Agent Assurance Platform",
  description: "Continuous, evidence-backed trust validation for SCM AI agents",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning className={displayFont.variable}>
      <body className="min-h-screen bg-background font-sans antialiased">
        <Providers>
          <TopNav />
          <main className="mx-auto max-w-7xl px-6 py-8">{children}</main>
        </Providers>
      </body>
    </html>
  );
}
