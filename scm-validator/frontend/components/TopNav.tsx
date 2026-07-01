"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Moon, Sun } from "lucide-react";
import { Button } from "./ui/button";
import ApiKeyControl from "./ApiKeyControl";
import CirceLogo from "./CirceLogo";
import { useThemeStore } from "../lib/store";
import { cn } from "../lib/utils";

const LINKS = [
  { href: "/new", label: "New Validation" },
  { href: "/history", label: "History" },
  { href: "/compare", label: "Compare" },
];

export default function TopNav() {
  const pathname = usePathname();
  const { theme, toggleTheme } = useThemeStore();

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
          <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label="Toggle theme" className="ml-2">
            {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>
        </nav>
      </div>
    </header>
  );
}
