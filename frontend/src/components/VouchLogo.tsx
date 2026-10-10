import React from "react";
import Image from "next/image";

interface VouchLogoProps {
  className?: string;
  size?: number;
  showWordmark?: boolean;
  variant?: "light" | "dark" | "auto";
  useImage?: boolean;
  subtext?: boolean;
}

/**
 * SriLekh Brand Logo Component
 * Displays the official squircle Rupee emblem and SriLekh (श्रीलेख Accounting) wordmark.
 */
export const VouchLogo: React.FC<VouchLogoProps> = ({
  className = "",
  size = 32,
  showWordmark = true,
  variant = "auto",
  subtext = true,
}) => {
  return (
    <div className={`inline-flex items-center gap-2.5 select-none ${className}`}>
      {/* Emblem / Badge */}
      <div 
        className="relative shrink-0 flex items-center justify-center overflow-hidden rounded-lg shadow-2xs"
        style={{ width: size, height: size }}
      >
        <Image
          src="/logo-mark.png"
          alt="SriLekh"
          width={size * 2}
          height={size * 2}
          priority
          className="object-contain w-full h-full"
        />
      </div>

      {/* Wordmark */}
      {showWordmark && (
        <div className="flex items-center leading-none">
          <span
            className={`font-black tracking-tight text-xl leading-none ${
              variant === "light"
                ? "text-[#162C5B]"
                : variant === "dark"
                ? "text-white"
                : "text-[#162C5B] dark:text-white"
            }`}
            style={{ fontFamily: "Georgia, Cambria, 'Times New Roman', serif" }}
          >
            SriLekh
          </span>
        </div>
      )}
    </div>
  );
};

export const SriLekhLogo = VouchLogo;
export default VouchLogo;
