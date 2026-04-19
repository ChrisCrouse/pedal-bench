import { forwardRef, type InputHTMLAttributes } from "react";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...rest }, ref) => {
    const classes = [
      "block w-full rounded-md border border-zinc-300 bg-white px-3 py-1.5",
      "text-sm shadow-sm placeholder:text-zinc-400",
      "focus:border-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/30",
      "disabled:opacity-50 disabled:cursor-not-allowed",
      "dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 dark:placeholder:text-zinc-500",
      className ?? "",
    ].join(" ");
    return <input ref={ref} className={classes} {...rest} />;
  },
);
Input.displayName = "Input";
