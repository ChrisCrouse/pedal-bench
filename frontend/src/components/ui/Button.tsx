import { forwardRef, type ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-emerald-600 text-white hover:bg-emerald-500 disabled:bg-emerald-600/50 shadow-sm",
  secondary:
    "bg-zinc-200 text-zinc-900 hover:bg-zinc-300 disabled:opacity-50 dark:bg-zinc-800 dark:text-zinc-100 dark:hover:bg-zinc-700",
  ghost:
    "bg-transparent text-zinc-700 hover:bg-zinc-100 disabled:opacity-50 dark:text-zinc-300 dark:hover:bg-zinc-800",
  danger:
    "bg-red-600 text-white hover:bg-red-500 disabled:bg-red-600/50 shadow-sm",
};

const SIZES: Record<Size, string> = {
  sm: "px-2.5 py-1 text-sm",
  md: "px-3.5 py-1.5 text-sm",
  lg: "px-5 py-2.5 text-base",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = "secondary", size = "md", className, ...rest }, ref) => {
    const classes = [
      "inline-flex items-center justify-center gap-1.5 rounded-md font-medium",
      "transition focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/50",
      "disabled:cursor-not-allowed",
      VARIANTS[variant],
      SIZES[size],
      className ?? "",
    ].join(" ");
    return <button ref={ref} className={classes} {...rest} />;
  },
);
Button.displayName = "Button";
