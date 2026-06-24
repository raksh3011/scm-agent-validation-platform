"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/new", label: "New Validation" },
  { href: "/history", label: "History" },
];

export default function TopNav() {
  const pathname = usePathname();
  return (
    <div className="topnav">
      <Link href="/new" className="brand">SCM Agent Validation</Link>
      <nav>
        {LINKS.map((l) => (
          <Link key={l.href} href={l.href} className={pathname.startsWith(l.href) ? "active" : ""}>
            {l.label}
          </Link>
        ))}
      </nav>
    </div>
  );
}
