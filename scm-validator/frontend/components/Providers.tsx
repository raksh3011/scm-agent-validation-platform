"use client";

import { useEffect, useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { hydrateTheme } from "../lib/store";

export default function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(() => new QueryClient());

  useEffect(() => {
    hydrateTheme();
  }, []);

  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
