import React from "react";
import Image from "next/image";

interface VouchLogoProps {
  className?: string;
  size?: number;
  showWordmark?: boolean;
  variant?: "light" | "dark" | "auto";
  useImage?: boolean;
}

/**
 * Vouch Brand Logo Component
 * Combines the Ledger-Wings emblem with geometric modern wordmark.
 */
export const VouchLogo: React.FC<VouchLogoProps> = ({
  className = "",
  size = 32,
  showWordmark = true,
  variant = "auto",
  useImage = true,
}) => {
  return (
    <div className={`inline-flex items-center gap-2.5 select-none ${className}`}>
      {/* Emblem */}
      {useImage ? (
        <div 
          className="relative shrink-0 flex items-center justify-center"
          style={{ width: size, height: size }}
        >
          <Image
            src="/logo-mark.png"
            alt="Vouch"
            width={size}
            height={size}
            priority
            className="object-contain w-full h-full"
          />
        </div>
      ) : (
        <svg
          width={size}
          height={size}
          viewBox="0 0 100 100"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className="shrink-0"
        >
          {/* Left Wing - Cyan Upper Accent */}
          <path d="M20 22L36 34L40 22C33 22 26 22 20 22Z" fill="#00B4D8" />
          {/* Right Wing - Cyan Upper Accent */}
          <path d="M80 22L64 34L60 22C67 22 74 22 80 22Z" fill="#00B4D8" />

          {/* Left Wing - Dark Navy Upper Main Body */}
          <path
            d="M17 22L19 46L36 37L20 22H17Z"
            className={
              variant === "light"
                ? "fill-[#0B1938]"
                : variant === "dark"
                ? "fill-slate-100"
                : "fill-[#0B1938] dark:fill-white"
            }
          />
          {/* Right Wing - Dark Navy Upper Main Body */}
          <path
            d="M83 22L81 46L64 37L80 22H83Z"
            className={
              variant === "light"
                ? "fill-[#0B1938]"
                : variant === "dark"
                ? "fill-slate-100"
                : "fill-[#0B1938] dark:fill-white"
            }
          />

          {/* Left Wing - Lower Body / Ledger Page */}
          <path
            d="M21 50L49 78V40L37 40L21 50Z"
            className={
              variant === "light"
                ? "fill-[#0B1938]"
                : variant === "dark"
                ? "fill-slate-200"
                : "fill-[#0B1938] dark:fill-slate-100"
            }
          />
          {/* Right Wing - Lower Body / Ledger Page */}
          <path
            d="M79 50L51 78V40L63 40L79 50Z"
            className={
              variant === "light"
                ? "fill-[#0B1938]"
                : variant === "dark"
                ? "fill-slate-200"
                : "fill-[#0B1938] dark:fill-slate-100"
            }
          />

          {/* Central Spine Negative Accent */}
          <path d="M49 42V75L35 37H44L49 42Z" fill="#00B4D8" opacity="0.9" />
          <path d="M51 42V75L65 37H56L51 42Z" fill="#00B4D8" opacity="0.9" />
        </svg>
      )}

      {/* Wordmark */}
      {showWordmark && (
        <span
          className={`font-black tracking-wider text-xl leading-none uppercase ${
            variant === "light"
              ? "text-[#0B1938]"
              : variant === "dark"
              ? "text-white"
              : "text-[#0B1938] dark:text-white"
          }`}
          style={{ letterSpacing: "0.14em" }}
        >
          Vouch
        </span>
      )}
    </div>
  );
};

export default VouchLogo;
