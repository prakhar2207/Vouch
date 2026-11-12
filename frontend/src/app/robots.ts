import type { MetadataRoute } from "next";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: [
          "/",
          "/pricing",
          "/contact",
          "/privacy-policy",
          "/terms",
          "/refund-policy",
          "/login",
          "/register",
        ],
        disallow: [
          "/admin",
          "/analytics",
          "/audit",
          "/banking",
          "/claim",
          "/dashboard",
          "/export",
          "/forgot-password",
          "/gst",
          "/health",
          "/import",
          "/inventory",
          "/ledgers",
          "/network",
          "/new-invoice",
          "/parties",
          "/purchases",
          "/reports",
          "/reset-password",
          "/sales",
          "/settings",
          "/share",
          "/voucher",
          "/vouchers",
          "/api",
        ],
      },
    ],
    sitemap: "https://srilekh.com/sitemap.xml",
  };
}
