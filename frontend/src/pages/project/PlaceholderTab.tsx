import type { ReactNode } from "react";

export function PlaceholderTab({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children?: ReactNode;
}) {
  return (
    <div className="mx-auto max-w-3xl px-6 py-16 text-center">
      <div className="text-xl font-semibold">{title}</div>
      <p className="mx-auto mt-2 max-w-lg text-sm text-zinc-600 dark:text-zinc-400">
        {description}
      </p>
      {children}
    </div>
  );
}
