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
 * ShriLekh Brand Logo Component
 * Displays the official squircle Rupee emblem and ShriLekh (श्रीलेख Accounting) wordmark.
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
          alt="ShriLekh"
          width={size * 2}
          height={size * 2}
          priority
          className="object-contain w-full h-full"
        />
      </div>

      {/* Wordmark */}
      {showWordmark && (
        <div className="flex flex-col justify-center leading-none">
          <span
            className={`font-black tracking-tight text-xl leading-none ${
              variant === "light"
                ? "text-[#183B7E]"
                : variant === "dark"
                ? "text-white"
                : "text-[#183B7E] dark:text-white"
            }`}
            style={{ fontFamily: "Georgia, Cambria, 'Times New Roman', serif" }}
          >
            ShriLekh
          </span>
          {subtext && (
            <span className="text-[10px] tracking-wider font-semibold text-[#D97706] dark:text-[#FBBF24] leading-tight mt-0.5">
              श्रीलेख <span className="text-[9px] text-muted-foreground font-normal tracking-widest uppercase ml-0.5">Accounting</span>
            </span>
          )}
        </div>
      )}
    </div>
  );
};

export const ShriLekhLogo = VouchLogo;
export default VouchLogo;
