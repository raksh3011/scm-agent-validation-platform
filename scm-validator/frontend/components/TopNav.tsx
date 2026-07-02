"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import ApiKeyControl from "./ApiKeyControl";
import CirceLogo from "./CirceLogo";
import { cn } from "../lib/utils";

const LINKS = [
  { href: "/new", label: "New Validation" },
  { href: "/history", label: "History" },
  { href: "/compare", label: "Compare" },
];

export default function TopNav() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-40 border-b border-border/60 bg-background/85 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
        <Link href="/new">
          <CirceLogo markClassName="h-8 w-8" wordmarkClassName="text-xl font-semibold tracking-tight" />
        </Link>
        <nav className="flex items-center gap-1">
          {LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className={cn(
                "rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground",
                pathname.startsWith(l.href) && "bg-accent text-accent-foreground"
              )}
            >
              {l.label}
            </Link>
          ))}
          <ApiKeyControl />
        </nav>
      </div>
    </header>
  );
}
