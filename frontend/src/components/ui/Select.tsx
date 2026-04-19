import { forwardRef, type SelectHTMLAttributes } from "react";

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, children, ...rest }, ref) => {
    const classes = [
      "block rounded-md border border-zinc-300 bg-white px-3 py-1.5",
      "text-sm shadow-sm",
      "focus:border-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/30",
      "disabled:opacity-50 disabled:cursor-not-allowed",
      "dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100",
      className ?? "",
    ].join(" ");
    return (
      <select ref={ref} className={classes} {...rest}>
        {children}
      </select>
    );
  },
);
Select.displayName = "Select";
