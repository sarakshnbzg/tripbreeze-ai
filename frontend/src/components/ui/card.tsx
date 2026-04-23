import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export function Card({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "glass-panel rounded-xl2 border border-white/75 shadow-card",
        className,
      )}
      {...props}
    />
  );
}
