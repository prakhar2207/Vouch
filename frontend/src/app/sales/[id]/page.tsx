"use client";
import { useEffect, Suspense } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";

function SalesInvoiceRedirectContent() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const id = params?.id as string;

  useEffect(() => {
    if (id) {
      const queryString = searchParams?.toString();
      const target = `/sales/${id}/print${queryString ? `?${queryString}` : ""}`;
      router.replace(target);
    }
  }, [id, searchParams, router]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-white text-slate-800 font-sans p-4">
      <div className="text-center space-y-2">
        <div className="w-8 h-8 border-3 border-emerald-500 border-t-transparent rounded-full animate-spin mx-auto"></div>
        <p className="text-sm font-medium text-slate-600">Loading invoice...</p>
      </div>
    </div>
  );
}

export default function SalesInvoiceRedirectPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center bg-white text-slate-800 font-sans p-4">
          <div className="text-center space-y-2">
            <div className="w-8 h-8 border-3 border-emerald-500 border-t-transparent rounded-full animate-spin mx-auto"></div>
            <p className="text-sm font-medium text-slate-600">Loading invoice...</p>
          </div>
        </div>
      }
    >
      <SalesInvoiceRedirectContent />
    </Suspense>
  );
}
