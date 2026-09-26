import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Vouch Accounting & ERP",
    short_name: "Vouch",
    description: "High-Speed Double-Entry Accounting & ERP with AI Accounts Payable and GST Compliance",
    start_url: "/dashboard",
    display: "standalone",
    display_override: ["window-controls-overlay", "standalone"],
    background_color: "#ffffff",
    theme_color: "#0B1938",
    icons: [
      {
        src: "/icons/icon-192x192.png?v=2",
        sizes: "192x192",
        type: "image/png",
      },
      {
        src: "/icons/icon-512x512.png?v=2",
        sizes: "512x512",
        type: "image/png",
      },
      {
        src: "/icons/icon-512x512.png?v=2",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
