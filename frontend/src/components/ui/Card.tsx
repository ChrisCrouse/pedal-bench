import type { HTMLAttributes, ReactNode } from "react";

export function Card({ className, children, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`rounded-lg border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-900 ${className ?? ""}`}
      {...rest}
    >
      {children}
    </div>
  );
}

export function CardHeader({ children }: { children: ReactNode }) {
  return (
    <div className="border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">{children}</div>
  );
}

export function CardBody({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={`px-4 py-3 ${className ?? ""}`}>{children}</div>;
}
