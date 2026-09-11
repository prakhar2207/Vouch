"use client";

import * as React from "react";
import { Moon, Sun, Monitor } from "lucide-react";
import { useTheme } from "next-themes";

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = React.useState(false);

  React.useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return <div className="w-9 h-9" />;
  }

  const cycleTheme = () => {
    if (theme === "light") setTheme("dark");
    else if (theme === "dark") setTheme("system");
    else setTheme("light");
  };

  const getLabel = () => {
    if (theme === "light") return "Light Theme (click for Dark)";
    if (theme === "dark") return "Dark Theme (click for System)";
    return "System Theme (click for Light)";
  };

  return (
    <button
      onClick={cycleTheme}
      className="w-9 h-9 rounded-lg border border-border/50 bg-muted/20 hover:bg-muted/60 text-muted-foreground hover:text-foreground transition-all cursor-pointer shadow-2xs flex items-center justify-center shrink-0"
      title={getLabel()}
      aria-label={getLabel()}
    >
      {theme === "dark" ? (
        <Moon className="h-4 w-4" />
      ) : theme === "light" ? (
        <Sun className="h-4 w-4" />
      ) : (
        <Monitor className="h-4 w-4" />
      )}
    </button>
  );
}
