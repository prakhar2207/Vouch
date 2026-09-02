"use client";

import { API_BASE_URL } from "@/utils/api";
import { useState, useRef } from "react";
import axios from "axios";
import { setTokens } from "@/utils/auth";
import { useRouter } from "next/navigation";
import Link from "next/link";
import StateSelect from "@/components/StateSelect";
import { UploadCloud, CheckCircle2, Image as ImageIcon, X, AlertCircle } from "lucide-react";

export default function Register() {
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Step 1: Auth
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  // Step 2: Firm Details
  const [firmName, setFirmName] = useState("");
  const [gstin, setGstin] = useState("");
  const [phone, setPhone] = useState("");
  const [companyEmail, setCompanyEmail] = useState("");
  const [address, setAddress] = useState("");
  const [stateCode, setStateCode] = useState("");

  // Step 3: Proprietor Details & Signature
  const [proprietorName, setProprietorName] = useState("");
  const [proprietorPhone, setProprietorPhone] = useState("");
  const [signatureFile, setSignatureFile] = useState<File | null>(null);
  const [signaturePreview, setSignaturePreview] = useState<string | null>(null);

  const handleNext = (e: React.FormEvent) => {
    e.preventDefault();
    if (step === 1 && (!email || !password)) return;
    if (step === 2 && (!firmName || !gstin || !phone || !address || !stateCode)) return;
    setStep(step + 1);
  };

  const handleSignatureChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setSignatureFile(file);
      const reader = new FileReader();
      reader.onload = (event) => {
        setSignaturePreview(event.target?.result as string);
      };
      reader.readAsDataURL(file);
    }
  };

  const removeSignature = () => {
    setSignatureFile(null);
    setSignaturePreview(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      const formData = new FormData();
      formData.append("email", email.trim().toLowerCase());
      formData.append("password", password);
      formData.append("name", firmName.trim());
      formData.append("gstin", gstin.trim().toUpperCase());
      formData.append("phone", phone.trim());
      formData.append("company_email", (companyEmail || email).trim());
      formData.append("address", address.trim());
      formData.append("state_code", stateCode.trim());
      formData.append("proprietor_name", proprietorName.trim());
      formData.append("proprietor_phone", proprietorPhone.trim());

      if (signatureFile) {
        formData.append("signature", signatureFile);
      }

      const res = await axios.post(`${API_BASE_URL}/api/v1/auth/register/`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });

      if (res.data.success) {
        setTokens(res.data.access, res.data.refresh);
        router.push("/dashboard");
      } else {
        setError(res.data.error || "Registration failed. Please check your details.");
      }
    } catch (err: any) {
      if (err.response?.data?.error) {
        setError(err.response.data.error);
      } else if (err.response?.data?.message) {
        setError(err.response.data.message);
      } else if (!err.response || err.message?.includes("Network Error") || err.code === "ERR_NETWORK") {
        setError(
          `Unable to connect to backend server (${API_BASE_URL}). If using Render free tier, the server may take ~30s to wake up on first request. Please wait a moment and click Complete Registration again.`
        );
      } else {
        setError(`Registration error: ${err.message || "Please check your details and try again."}`);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background text-foreground py-12 px-4">
      <div className="bg-card text-card-foreground p-8 rounded-2xl shadow-xl border border-border w-full max-w-lg">
        
        {/* Header */}
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-black mb-2 tracking-tight">Create your Vouch Account</h1>
          <p className="text-gray-400 text-xs">
            Step {step} of 3: {step === 1 ? "Account Credentials" : step === 2 ? "Firm & GSTIN Details" : "Proprietor & Signature"}
          </p>
          <div className="flex gap-2 justify-center mt-4">
            <div className={`h-1.5 w-12 rounded-full transition-all ${step >= 1 ? "bg-blue-600" : "bg-zinc-800"}`}></div>
            <div className={`h-1.5 w-12 rounded-full transition-all ${step >= 2 ? "bg-blue-600" : "bg-zinc-800"}`}></div>
            <div className={`h-1.5 w-12 rounded-full transition-all ${step >= 3 ? "bg-blue-600" : "bg-zinc-800"}`}></div>
          </div>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/30 text-red-400 p-3.5 rounded-xl mb-6 text-xs flex items-start gap-2 animate-in fade-in">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={step === 3 ? handleRegister : handleNext} className="space-y-5">
          
          {/* STEP 1: AUTH */}
          {step === 1 && (
            <div className="space-y-4 animate-in fade-in duration-200">
              <div>
                <label className="block text-xs font-semibold mb-1.5 text-gray-300">Login Email *</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  className="w-full bg-zinc-900 border border-zinc-700 p-3 rounded-xl text-xs text-white placeholder-gray-500 focus:ring-2 focus:ring-blue-500 outline-none"
                  placeholder="admin@yourbusiness.com"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold mb-1.5 text-gray-300">Password *</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={6}
                  className="w-full bg-zinc-900 border border-zinc-700 p-3 rounded-xl text-xs text-white placeholder-gray-500 focus:ring-2 focus:ring-blue-500 outline-none"
                  placeholder="•••••••• (Min 6 chars)"
                />
              </div>
            </div>
          )}

          {/* STEP 2: FIRM DETAILS */}
          {step === 2 && (
            <div className="space-y-4 animate-in fade-in duration-200">
              <div>
                <label className="block text-xs font-semibold mb-1.5 text-gray-300">Firm Name *</label>
                <input
                  type="text"
                  value={firmName}
                  onChange={(e) => setFirmName(e.target.value)}
                  required
                  className="w-full bg-zinc-900 border border-zinc-700 p-3 rounded-xl text-xs text-white placeholder-gray-500 focus:ring-2 focus:ring-blue-500 outline-none"
                  placeholder="Acme Industrial Supplies Pvt Ltd"
                />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold mb-1.5 text-gray-300">GSTIN *</label>
                  <input
                    type="text"
                    value={gstin}
                    onChange={(e) => setGstin(e.target.value.toUpperCase())}
                    required
                    className="w-full bg-zinc-900 border border-zinc-700 p-3 rounded-xl text-xs text-white placeholder-gray-500 focus:ring-2 focus:ring-blue-500 outline-none font-mono uppercase"
                    placeholder="27AAACA1234A1Z5"
                    maxLength={15}
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold mb-1.5 text-gray-300">Mobile No. *</label>
                  <input
                    type="tel"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    required
                    className="w-full bg-zinc-900 border border-zinc-700 p-3 rounded-xl text-xs text-white placeholder-gray-500 focus:ring-2 focus:ring-blue-500 outline-none font-mono"
                    placeholder="9876543210"
                  />
                </div>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold mb-1.5 text-gray-300">Company Email (Optional)</label>
                  <input
                    type="email"
                    value={companyEmail}
                    onChange={(e) => setCompanyEmail(e.target.value)}
                    className="w-full bg-zinc-900 border border-zinc-700 p-3 rounded-xl text-xs text-white placeholder-gray-500 focus:ring-2 focus:ring-blue-500 outline-none"
                    placeholder="sales@business.com"
                  />
                </div>
                <div>
                  <StateSelect
                    value={stateCode}
                    onChange={(code) => setStateCode(code)}
                    label="State / Union Territory *"
                    placeholder="Search state..."
                    required
                  />
                </div>
              </div>
              <div>
                <label className="block text-xs font-semibold mb-1.5 text-gray-300">Billing Address *</label>
                <textarea
                  value={address}
                  onChange={(e) => setAddress(e.target.value)}
                  required
                  rows={2}
                  className="w-full bg-zinc-900 border border-zinc-700 p-3 rounded-xl text-xs text-white placeholder-gray-500 focus:ring-2 focus:ring-blue-500 outline-none resize-none"
                  placeholder="Plot 42, Industrial Area, City..."
                />
              </div>
            </div>
          )}

          {/* STEP 3: PROPRIETOR DETAILS & SIGNATURE UPLOAD */}
          {step === 3 && (
            <div className="space-y-4 animate-in fade-in duration-200">
              <div className="bg-blue-500/10 border border-blue-500/20 p-3.5 rounded-xl">
                <p className="text-xs text-blue-300 leading-relaxed">
                  <strong className="text-blue-400">Invoice Readiness:</strong> These details appear on your printed GST Tax Invoices and Authorized Signatory stamp.
                </p>
              </div>
              
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold mb-1.5 text-gray-300">Proprietor / Signatory Name</label>
                  <input
                    type="text"
                    value={proprietorName}
                    onChange={(e) => setProprietorName(e.target.value)}
                    className="w-full bg-zinc-900 border border-zinc-700 p-3 rounded-xl text-xs text-white placeholder-gray-500 focus:ring-2 focus:ring-blue-500 outline-none"
                    placeholder="e.g. Rahul Sharma"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold mb-1.5 text-gray-300">Proprietor Phone</label>
                  <input
                    type="tel"
                    value={proprietorPhone}
                    onChange={(e) => setProprietorPhone(e.target.value)}
                    className="w-full bg-zinc-900 border border-zinc-700 p-3 rounded-xl text-xs text-white placeholder-gray-500 focus:ring-2 focus:ring-blue-500 outline-none font-mono"
                    placeholder="9876543210"
                  />
                </div>
              </div>

              {/* Digital Signature File Upload */}
              <div>
                <label className="block text-xs font-semibold mb-1.5 text-gray-300">
                  Digital Signature Image (Optional)
                </label>
                
                <input
                  type="file"
                  ref={fileInputRef}
                  onChange={handleSignatureChange}
                  accept="image/png, image/jpeg, image/webp"
                  className="hidden"
                />

                {signaturePreview ? (
                  <div className="p-4 bg-zinc-900 border border-zinc-700 rounded-xl flex items-center justify-between gap-4">
                    <div className="flex items-center gap-3">
                      <div className="w-16 h-12 bg-white rounded-lg p-1 flex items-center justify-center overflow-hidden border border-zinc-600">
                        <img src={signaturePreview} alt="Signature Preview" className="max-h-full object-contain" />
                      </div>
                      <div>
                        <div className="text-xs font-bold text-white truncate max-w-[180px]">
                          {signatureFile?.name || "signature.png"}
                        </div>
                        <div className="text-[10px] text-green-400 flex items-center gap-1">
                          <CheckCircle2 className="w-3 h-3" />
                          <span>Signature loaded</span>
                        </div>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={removeSignature}
                      className="p-1.5 text-gray-400 hover:text-red-400 hover:bg-zinc-800 rounded-lg transition-colors cursor-pointer"
                      title="Remove signature"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                ) : (
                  <div
                    onClick={() => fileInputRef.current?.click()}
                    className="border-2 border-dashed border-zinc-700 hover:border-blue-500/60 rounded-xl p-6 text-center bg-zinc-900/40 hover:bg-zinc-900/80 transition-all cursor-pointer space-y-2"
                  >
                    <div className="w-10 h-10 rounded-full bg-zinc-800 text-blue-400 flex items-center justify-center mx-auto">
                      <UploadCloud className="w-5 h-5" />
                    </div>
                    <div className="text-xs font-semibold text-gray-200">
                      Click to upload Signature image
                    </div>
                    <p className="text-[10px] text-gray-500">
                      PNG, JPG, or WEBP (Transparent background recommended)
                    </p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Form Actions */}
          <div className="flex gap-3 pt-4 border-t border-zinc-800">
            {step > 1 && (
              <button
                type="button"
                onClick={() => setStep(step - 1)}
                className="flex-1 bg-zinc-800 text-gray-200 py-3 rounded-xl text-xs font-bold hover:bg-zinc-700 transition-colors cursor-pointer"
              >
                Back
              </button>
            )}
            
            <button
              type="submit"
              disabled={loading}
              className="flex-1 bg-blue-600 text-white py-3 rounded-xl text-xs font-bold hover:bg-blue-700 transition-colors shadow-lg shadow-blue-600/25 disabled:opacity-50 cursor-pointer flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
                  <span>Creating Account...</span>
                </>
              ) : step === 3 ? (
                "Complete Registration"
              ) : (
                "Next Step →"
              )}
            </button>
          </div>
          
        </form>

        <div className="mt-6 text-center text-xs text-gray-500">
          Already have an account?{" "}
          <Link href="/login" className="text-blue-400 hover:underline font-semibold">
            Log in
          </Link>
        </div>
      </div>
    </div>
  );
}
