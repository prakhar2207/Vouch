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
    return <div className="w-[104px] h-9" />; // Placeholder
  }

  return (
    <div className="flex items-center gap-1 bg-gray-100 dark:bg-zinc-800 p-1 rounded-lg border border-border">
      <button
        onClick={() => setTheme("light")}
        className={`p-1.5 rounded-md transition-colors ${
          theme === "light"
            ? "bg-white text-black shadow-sm dark:bg-transparent dark:text-gray-400"
            : "text-gray-500 hover:text-black dark:text-gray-400 dark:hover:text-gray-300"
        }`}
        title="Light"
      >
        <Sun className="h-4 w-4" />
      </button>
      <button
        onClick={() => setTheme("dark")}
        className={`p-1.5 rounded-md transition-colors ${
          theme === "dark"
            ? "bg-zinc-700 text-white shadow-sm"
            : "text-gray-500 hover:text-black dark:text-gray-400 dark:hover:text-gray-300"
        }`}
        title="Dark"
      >
        <Moon className="h-4 w-4" />
      </button>
      <button
        onClick={() => setTheme("system")}
        className={`p-1.5 rounded-md transition-colors ${
          theme === "system"
            ? "bg-white text-black shadow-sm dark:bg-zinc-700 dark:text-white"
            : "text-gray-500 hover:text-black dark:text-gray-400 dark:hover:text-gray-300"
        }`}
        title="System"
      >
        <Monitor className="h-4 w-4" />
      </button>
    </div>
  );
}
