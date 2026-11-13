"use client";

import { API_BASE_URL } from "@/utils/api";
import { useState, useRef, useEffect } from "react";
import axios from "axios";
import { isCapacitorNative, setAuthenticatedSession } from "@/utils/auth";
import { useRouter } from "next/navigation";
import Link from "next/link";
import StateSelect from "@/components/StateSelect";
import {
  UploadCloud,
  CheckCircle2,
  Image as ImageIcon,
  X,
  AlertCircle,
  FileSpreadsheet,
  ArrowRight,
  ArrowLeft,
  Sparkles,
  LayoutDashboard,
  ShieldCheck,
  Mail,
  RefreshCw,
} from "lucide-react";

export default function Register() {
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Pre-warm backend container
  useEffect(() => {
    try {
      fetch(`${API_BASE_URL}/api/health/`, { method: "GET", keepalive: true }).catch(() => {});
    } catch {
      // Passive warm-up attempt
    }
  }, []);

  // Step 1: Auth Credentials
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [sessionToken, setSessionToken] = useState("");

  // Step 2: 6-Digit OTP
  const [otpDigits, setOtpDigits] = useState(["", "", "", "", "", ""]);
  const [resendCooldown, setResendCooldown] = useState(60);
  const [canResend, setCanResend] = useState(false);
  const [registrationToken, setRegistrationToken] = useState("");
  const otpInputRefs = useRef<(HTMLInputElement | null)[]>([]);

  // Timer countdown for OTP resend
  useEffect(() => {
    let timer: NodeJS.Timeout;
    if (step === 2 && resendCooldown > 0) {
      setCanResend(false);
      timer = setInterval(() => {
        setResendCooldown((prev) => {
          if (prev <= 1) {
            setCanResend(true);
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
    } else if (resendCooldown === 0) {
      setCanResend(true);
    }
    return () => clearInterval(timer);
  }, [step, resendCooldown]);

  // Step 3: Firm Details & GST Registration
  const [isGstRegistered, setIsGstRegistered] = useState(true);
  const [firmName, setFirmName] = useState("");
  const [gstin, setGstin] = useState("");
  const [phone, setPhone] = useState("");
  const [companyEmail, setCompanyEmail] = useState("");
  const [address, setAddress] = useState("");
  const [stateCode, setStateCode] = useState("");

  // Step 4: Proprietor Details & Signature
  const [proprietorName, setProprietorName] = useState("");
  const [proprietorPhone, setProprietorPhone] = useState("");
  const [signatureFile, setSignatureFile] = useState<File | null>(null);
  const [signaturePreview, setSignaturePreview] = useState<string | null>(null);

  // Handle OTP Digit Input Navigation
  const handleOtpChange = (index: number, value: string) => {
    if (value.length > 1) {
      // Handle paste of complete 6-digit code
      const pasted = value.replace(/\D/g, "").slice(0, 6);
      if (pasted.length > 0) {
        const newDigits = [...otpDigits];
        for (let i = 0; i < 6; i++) {
          newDigits[i] = pasted[i] || "";
        }
        setOtpDigits(newDigits);
        const nextIndex = Math.min(pasted.length, 5);
        otpInputRefs.current[nextIndex]?.focus();
      }
      return;
    }

    const digit = value.replace(/\D/g, "");
    const newDigits = [...otpDigits];
    newDigits[index] = digit;
    setOtpDigits(newDigits);

    // Auto advance focus to next box
    if (digit && index < 5) {
      otpInputRefs.current[index + 1]?.focus();
    }
  };

  const handleOtpKeyDown = (index: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Backspace" && !otpDigits[index] && index > 0) {
      otpInputRefs.current[index - 1]?.focus();
    }
  };

  // Step 1 Submission: Initiate Email OTP
  const handleInitiateOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!email.trim() || !password) {
      setError("Please enter your email and password to continue.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters long.");
      return;
    }
    if (confirmPassword && password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setLoading(true);
    try {
      const res = await axios.post(`${API_BASE_URL}/api/v1/auth/register/initiate/`, {
        email: email.trim().toLowerCase(),
        password,
        confirm_password: confirmPassword,
      });

      if (res.data.success) {
        setSessionToken(res.data.session_token);
        setResendCooldown(res.data.resend_cooldown || 60);
        setStep(2);
        setTimeout(() => otpInputRefs.current[0]?.focus(), 100);
      } else {
        setError(res.data.error || "Unable to send verification code.");
      }
    } catch (err: any) {
      setError(err.response?.data?.error || "Error initiating registration. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  // Step 2 Submission: Verify OTP
  const handleVerifyOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    const otp = otpDigits.join("");
    if (otp.length !== 6) {
      setError("Please enter the complete 6-digit verification code.");
      return;
    }

    setLoading(true);
    setError("");
    try {
      const res = await axios.post(`${API_BASE_URL}/api/v1/auth/register/verify-otp/`, {
        session_token: sessionToken,
        otp,
      });

      if (res.data.success) {
        setRegistrationToken(res.data.registration_token);
        setStep(3);
      } else {
        setError(res.data.error || "Invalid verification code.");
      }
    } catch (err: any) {
      setError(err.response?.data?.error || "Invalid verification code. Please check and try again.");
    } finally {
      setLoading(false);
    }
  };

  // Step 2 Resend OTP
  const handleResendOtp = async () => {
    if (!canResend || loading) return;
    setLoading(true);
    setError("");
    try {
      const res = await axios.post(`${API_BASE_URL}/api/v1/auth/register/resend-otp/`, {
        session_token: sessionToken,
      });
      if (res.data.success) {
        setSessionToken(res.data.session_token);
        setResendCooldown(res.data.resend_cooldown || 60);
        setOtpDigits(["", "", "", "", "", ""]);
        otpInputRefs.current[0]?.focus();
      } else {
        setError(res.data.error || "Could not resend OTP.");
      }
    } catch (err: any) {
      setError(err.response?.data?.error || "Unable to resend OTP at this time.");
    } finally {
      setLoading(false);
    }
  };

  // Step 3 Next Button: Validate Firm Details
  const handleFirmNext = (e: React.FormEvent) => {
    e.preventDefault();
    if (!firmName.trim()) {
      setError("Please enter your business or firm name.");
      return;
    }
    if (isGstRegistered) {
      if (!gstin.trim()) {
        setError("Please enter your 15-digit GSTIN.");
        return;
      }
      if (gstin.trim().length !== 15) {
        setError("GSTIN must be exactly 15 alphanumeric characters.");
        return;
      }
    }
    if (!phone.trim()) {
      setError("Please enter your business contact phone number.");
      return;
    }
    if (!address.trim()) {
      setError("Please enter your business registered address.");
      return;
    }
    if (!stateCode.trim()) {
      setError("Please select your state / jurisdiction.");
      return;
    }
    setError("");
    setStep(4);
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

  // Step 4 Final Submission: Complete Registration
  const handleCompleteRegistration = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      const formData = new FormData();
      formData.append("registration_token", registrationToken);
      formData.append("name", firmName.trim());
      formData.append("is_gst_registered", isGstRegistered ? "true" : "false");
      if (isGstRegistered) {
        formData.append("gstin", gstin.trim().toUpperCase());
      }
      formData.append("phone", phone.trim());
      formData.append("company_email", (companyEmail || email).trim());
      formData.append("address", address.trim());
      formData.append("state_code", stateCode.trim());
      formData.append("proprietor_name", proprietorName.trim());
      formData.append("proprietor_phone", proprietorPhone.trim());

      if (signatureFile) {
        formData.append("signature", signatureFile);
      }

      const native = isCapacitorNative();
      const res = await axios.post(`${API_BASE_URL}/api/v1/auth/register/complete/`, formData, {
        withCredentials: !native,
        headers: {
          "Content-Type": "multipart/form-data",
          "X-Client-Type": native ? "capacitor" : "web",
        },
      });

      if (res.data.success) {
        setAuthenticatedSession({
          user: res.data.user,
          csrfToken: res.data.csrf_token,
          expiresAt: res.data.expires_at,
          refreshExpiresAt: res.data.refresh_expires_at,
          access: res.data.access,
          refresh: res.data.refresh,
        });
        setStep(5); // Move to Onboarding Setup & Migration screen
      } else {
        setError(res.data.error || "Registration failed. Please check your details.");
      }
    } catch (err: any) {
      setError(err.response?.data?.error || "Registration error. Please check your details and try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background text-foreground py-6 sm:py-12 px-3 sm:px-4">
      <div className={`bg-card text-card-foreground p-5 sm:p-8 rounded-2xl shadow-xl border border-border w-full ${step === 5 ? "max-w-2xl" : "max-w-lg"}`}>
        
        {/* Header */}
        <div className="mb-6 text-center">
          <h1 className="text-2xl font-black mb-1.5 tracking-tight">
            {step === 5 ? "Welcome to SriLekh! 🚀" : "Create your SriLekh Account"}
          </h1>
          <p className="text-muted-foreground text-xs">
            {step === 1 && "Step 1 of 4: Account Credentials"}
            {step === 2 && "Step 2 of 4: Verify Email Address"}
            {step === 3 && "Step 3 of 4: Firm & GST Details"}
            {step === 4 && "Step 4 of 4: Proprietor & Signature"}
            {step === 5 && "Onboarding: Setup & Migration"}
          </p>

          {/* Progress Bar */}
          {step <= 4 && (
            <div className="flex gap-2 justify-center mt-3">
              <div className={`h-1.5 w-10 rounded-full transition-all ${step >= 1 ? "bg-primary" : "bg-muted"}`}></div>
              <div className={`h-1.5 w-10 rounded-full transition-all ${step >= 2 ? "bg-primary" : "bg-muted"}`}></div>
              <div className={`h-1.5 w-10 rounded-full transition-all ${step >= 3 ? "bg-primary" : "bg-muted"}`}></div>
              <div className={`h-1.5 w-10 rounded-full transition-all ${step >= 4 ? "bg-primary" : "bg-muted"}`}></div>
            </div>
          )}
        </div>

        {/* Error Alert */}
        {error && (
          <div role="alert" className="bg-destructive/10 border border-destructive/20 text-destructive p-3 rounded-xl mb-5 text-xs flex items-start gap-2">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        {/* STEP 1: Account Credentials */}
        {step === 1 && (
          <form onSubmit={handleInitiateOtp} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold mb-1 text-foreground">Work / Business Email</label>
              <input
                type="email"
                className="w-full bg-muted/50 border border-input p-3 rounded-xl text-sm placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="owner@yourcompany.com"
                required
                autoFocus
              />
              <p className="text-[11px] text-muted-foreground mt-1">We will send a 6-digit verification code to this address.</p>
            </div>

            <div>
              <label className="block text-xs font-semibold mb-1 text-foreground">Password</label>
              <input
                type="password"
                className="w-full bg-muted/50 border border-input p-3 rounded-xl text-sm placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="At least 8 characters"
                required
              />
            </div>

            <div>
              <label className="block text-xs font-semibold mb-1 text-foreground">Confirm Password</label>
              <input
                type="password"
                className="w-full bg-muted/50 border border-input p-3 rounded-xl text-sm placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Re-enter your password"
                required
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full min-h-[44px] bg-primary text-primary-foreground p-3 rounded-xl font-bold text-sm hover:bg-primary/90 transition-all shadow-md shadow-primary/20 flex items-center justify-center gap-2 cursor-pointer disabled:opacity-75"
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <span className="w-4 h-4 border-2 border-primary-foreground/30 border-t-primary-foreground rounded-full animate-spin" />
                  Sending code...
                </span>
              ) : (
                <>
                  Continue with Email Verification <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>

            <div className="pt-3 text-center border-t border-border/50">
              <p className="text-xs text-muted-foreground">
                Already have an account?{" "}
                <Link href="/login" className="text-primary hover:underline font-semibold">
                  Sign In
                </Link>
              </p>
            </div>
          </form>
        )}

        {/* STEP 2: 6-Digit Email OTP Verification */}
        {step === 2 && (
          <form onSubmit={handleVerifyOtp} className="space-y-5 text-center">
            <div className="w-12 h-12 bg-primary/10 border border-primary/20 text-primary rounded-full flex items-center justify-center mx-auto mb-2">
              <Mail className="w-6 h-6" />
            </div>

            <div className="space-y-1">
              <h2 className="text-base font-bold text-foreground">Enter 6-digit verification code</h2>
              <p className="text-xs text-muted-foreground">
                We sent a one-time code to <strong className="text-foreground">{email}</strong>
              </p>
              <button
                type="button"
                onClick={() => setStep(1)}
                className="text-xs text-primary hover:underline font-medium"
              >
                Change email address
              </button>
            </div>

            {/* 6 Digit Input Boxes */}
            <div className="flex justify-center gap-2 sm:gap-3 py-2">
              {otpDigits.map((digit, idx) => (
                <input
                  key={idx}
                  ref={(el) => { otpInputRefs.current[idx] = el; }}
                  type="text"
                  inputMode="numeric"
                  maxLength={6}
                  value={digit}
                  onChange={(e) => handleOtpChange(idx, e.target.value)}
                  onKeyDown={(e) => handleOtpKeyDown(idx, e)}
                  className="w-11 h-13 sm:w-12 sm:h-14 text-center text-xl font-bold font-mono bg-muted/50 border-2 border-input focus:border-primary focus:bg-background rounded-xl focus:outline-none transition-all shadow-sm"
                />
              ))}
            </div>

            <p className="text-[11px] text-muted-foreground">Code is valid for 5 minutes.</p>

            <button
              type="submit"
              disabled={loading || otpDigits.join("").length !== 6}
              className="w-full min-h-[44px] bg-primary text-primary-foreground p-3 rounded-xl font-bold text-sm hover:bg-primary/90 transition-all shadow-md shadow-primary/20 flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <span className="w-4 h-4 border-2 border-primary-foreground/30 border-t-primary-foreground rounded-full animate-spin" />
                  Verifying code...
                </span>
              ) : (
                <>
                  <ShieldCheck className="w-4 h-4" /> Verify Email & Continue
                </>
              )}
            </button>

            {/* Resend Cooldown */}
            <div className="pt-2 text-xs">
              {canResend ? (
                <button
                  type="button"
                  onClick={handleResendOtp}
                  disabled={loading}
                  className="inline-flex items-center gap-1.5 text-primary hover:underline font-semibold cursor-pointer"
                >
                  <RefreshCw className="w-3.5 h-3.5" /> Resend verification code
                </button>
              ) : (
                <span className="text-muted-foreground">
                  Resend code in <strong className="text-foreground">{resendCooldown}s</strong>
                </span>
              )}
            </div>
          </form>
        )}

        {/* STEP 3: Firm Details & GST Registration */}
        {step === 3 && (
          <form onSubmit={handleFirmNext} className="space-y-4">
            {/* GST Registered Toggle */}
            <div className="bg-muted/40 border border-border p-3.5 rounded-xl space-y-2">
              <div className="flex items-center justify-between">
                <div>
                  <label className="text-xs font-bold text-foreground">Is your business GST Registered?</label>
                  <p className="text-[11px] text-muted-foreground">Unregistered retailers and composition firms can also register.</p>
                </div>
                <div className="flex items-center gap-2 bg-muted p-1 rounded-lg border border-border">
                  <button
                    type="button"
                    onClick={() => setIsGstRegistered(true)}
                    className={`px-3 py-1 rounded-md text-xs font-semibold transition-all ${isGstRegistered ? "bg-primary text-primary-foreground shadow" : "text-muted-foreground hover:text-foreground"}`}
                  >
                    Yes
                  </button>
                  <button
                    type="button"
                    onClick={() => { setIsGstRegistered(false); setGstin(""); }}
                    className={`px-3 py-1 rounded-md text-xs font-semibold transition-all ${!isGstRegistered ? "bg-primary text-primary-foreground shadow" : "text-muted-foreground hover:text-foreground"}`}
                  >
                    No
                  </button>
                </div>
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold mb-1 text-foreground">Business / Firm Legal Name *</label>
              <input
                type="text"
                className="w-full bg-muted/50 border border-input p-3 rounded-xl text-sm placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                value={firmName}
                onChange={(e) => setFirmName(e.target.value)}
                placeholder="e.g. Apex Industrial Supplies"
                required
              />
            </div>

            {isGstRegistered && (
              <div>
                <label className="block text-xs font-semibold mb-1 text-foreground">GSTIN (15 Digits) *</label>
                <input
                  type="text"
                  maxLength={15}
                  className="w-full bg-muted/50 border border-input p-3 rounded-xl text-sm font-mono uppercase placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                  value={gstin}
                  onChange={(e) => {
                    const val = e.target.value.toUpperCase();
                    setGstin(val);
                    if (val.length >= 2 && !stateCode) {
                      setStateCode(val.slice(0, 2));
                    }
                  }}
                  placeholder="27AABCU9603R1ZM"
                  required
                />
              </div>
            )}

            <div>
              <label className="block text-xs font-semibold mb-1 text-foreground">Business Contact Phone *</label>
              <input
                type="tel"
                maxLength={10}
                className="w-full bg-muted/50 border border-input p-3 rounded-xl text-sm placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                value={phone}
                onChange={(e) => setPhone(e.target.value.replace(/\D/g, ""))}
                placeholder="9876543210"
                required
              />
            </div>

            <div>
              <label className="block text-xs font-semibold mb-1 text-foreground">State / Jurisdiction *</label>
              <StateSelect
                value={stateCode}
                onChange={(val) => setStateCode(val)}
                className="w-full"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold mb-1 text-foreground">Registered Business Address *</label>
              <textarea
                rows={2}
                className="w-full bg-muted/50 border border-input p-3 rounded-xl text-sm placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring resize-none"
                value={address}
                onChange={(e) => setAddress(e.target.value)}
                placeholder="Shop No., Street, City, Pincode"
                required
              />
            </div>

            <div className="flex gap-3 pt-2">
              <button
                type="button"
                onClick={() => setStep(2)}
                className="w-1/3 min-h-[44px] bg-muted text-foreground p-3 rounded-xl font-semibold text-xs hover:bg-muted/80 transition-colors flex items-center justify-center gap-1.5"
              >
                <ArrowLeft className="w-3.5 h-3.5" /> Back
              </button>
              <button
                type="submit"
                className="w-2/3 min-h-[44px] bg-primary text-primary-foreground p-3 rounded-xl font-bold text-sm hover:bg-primary/90 transition-all shadow-md shadow-primary/20 flex items-center justify-center gap-2 cursor-pointer"
              >
                Next Step <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </form>
        )}

        {/* STEP 4: Proprietor & Signature */}
        {step === 4 && (
          <form onSubmit={handleCompleteRegistration} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold mb-1 text-foreground">Proprietor / Signatory Name</label>
              <input
                type="text"
                className="w-full bg-muted/50 border border-input p-3 rounded-xl text-sm placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                value={proprietorName}
                onChange={(e) => setProprietorName(e.target.value)}
                placeholder="e.g. Ramesh Kumar"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold mb-1 text-foreground">Proprietor Personal Phone</label>
              <input
                type="tel"
                maxLength={10}
                className="w-full bg-muted/50 border border-input p-3 rounded-xl text-sm placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                value={proprietorPhone}
                onChange={(e) => setProprietorPhone(e.target.value.replace(/\D/g, ""))}
                placeholder="Optional personal mobile"
              />
            </div>

            {/* Signature Upload */}
            <div>
              <label className="block text-xs font-semibold mb-1 text-foreground">
                Authorized Signature Image (Optional)
              </label>
              <p className="text-[11px] text-muted-foreground mb-2">
                Will be printed automatically on your invoices and vouchers.
              </p>

              {signaturePreview ? (
                <div className="relative border border-border rounded-xl p-3 bg-muted/20 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <img src={signaturePreview} alt="Signature Preview" className="h-12 max-w-[120px] object-contain rounded bg-white p-1" />
                    <span className="text-xs text-foreground font-medium truncate max-w-[160px]">
                      {signatureFile?.name}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={removeSignature}
                    className="p-1 hover:bg-muted rounded-full text-muted-foreground hover:text-foreground"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              ) : (
                <div
                  onClick={() => fileInputRef.current?.click()}
                  className="border-2 border-dashed border-border hover:border-primary/50 rounded-xl p-4 text-center cursor-pointer bg-muted/10 hover:bg-muted/20 transition-all"
                >
                  <UploadCloud className="w-6 h-6 text-muted-foreground mx-auto mb-1.5" />
                  <span className="text-xs font-medium text-foreground">Click to upload signature</span>
                  <p className="text-[10px] text-muted-foreground mt-0.5">PNG, JPG, or WEBP up to 5MB</p>
                </div>
              )}

              <input
                ref={fileInputRef}
                type="file"
                accept="image/*,.pdf"
                className="hidden"
                onChange={handleSignatureChange}
              />
            </div>

            <div className="flex gap-3 pt-2">
              <button
                type="button"
                onClick={() => setStep(3)}
                className="w-1/3 min-h-[44px] bg-muted text-foreground p-3 rounded-xl font-semibold text-xs hover:bg-muted/80 transition-colors flex items-center justify-center gap-1.5"
              >
                <ArrowLeft className="w-3.5 h-3.5" /> Back
              </button>
              <button
                type="submit"
                disabled={loading}
                className="w-2/3 min-h-[44px] bg-primary text-primary-foreground p-3 rounded-xl font-bold text-sm hover:bg-primary/90 transition-all shadow-md shadow-primary/20 flex items-center justify-center gap-2 cursor-pointer disabled:opacity-75"
              >
                {loading ? (
                  <span className="flex items-center gap-2">
                    <span className="w-4 h-4 border-2 border-primary-foreground/30 border-t-primary-foreground rounded-full animate-spin" />
                    Provisioning account...
                  </span>
                ) : (
                  <>
                    <CheckCircle2 className="w-4 h-4" /> Complete Registration
                  </>
                )}
              </button>
            </div>
          </form>
        )}

        {/* STEP 5: Onboarding Setup & Migration Selection */}
        {step === 5 && (
          <div className="space-y-6 animate-in fade-in duration-300">
            <div className="text-center space-y-1">
              <h2 className="text-lg sm:text-xl font-bold text-foreground">How would you like to set up your books?</h2>
              <p className="text-xs text-muted-foreground">
                You can migrate your existing business data in 60 seconds or start fresh with blank books.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div 
                onClick={() => router.push("/import?welcome=1")}
                className="group relative bg-gradient-to-b from-blue-500/10 via-background to-background border-2 border-blue-500/40 hover:border-blue-500 p-5 rounded-2xl cursor-pointer transition-all hover:shadow-lg hover:shadow-blue-500/10 flex flex-col justify-between"
              >
                <div className="absolute top-3 right-3 bg-blue-500 text-white text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider flex items-center gap-1 shadow-sm">
                  <Sparkles className="w-3 h-3" /> Recommended
                </div>

                <div>
                  <div className="w-12 h-12 rounded-xl bg-blue-500/20 text-blue-500 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
                    <FileSpreadsheet className="w-6 h-6" />
                  </div>
                  <h3 className="font-bold text-foreground text-base mb-1.5">Migrate Existing Data</h3>
                  <p className="text-xs text-muted-foreground leading-relaxed">
                    Import ledgers, stock items, and opening balances from <strong>Tally Prime / ERP 9</strong> or <strong>Excel / CSV</strong>.
                  </p>
                </div>

                <div className="mt-5 pt-3 border-t border-border/50 flex items-center text-xs font-bold text-blue-500 group-hover:translate-x-1 transition-transform">
                  Start 1-Click Migration &rarr;
                </div>
              </div>

              <div 
                onClick={() => router.push("/dashboard")}
                className="group relative bg-muted/30 hover:bg-muted/50 border border-border hover:border-foreground/20 p-5 rounded-2xl cursor-pointer transition-all flex flex-col justify-between"
              >
                <div>
                  <div className="w-12 h-12 rounded-xl bg-muted text-muted-foreground flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
                    <LayoutDashboard className="w-6 h-6" />
                  </div>
                  <h3 className="font-bold text-foreground text-base mb-1.5">Start Fresh</h3>
                  <p className="text-xs text-muted-foreground leading-relaxed">
                    Jump straight into your blank dashboard. Add parties and inventory items as you invoice.
                  </p>
                </div>

                <div className="mt-5 pt-3 border-t border-border/50 flex items-center text-xs font-semibold text-muted-foreground group-hover:text-foreground transition-colors">
                  Go to Dashboard &rarr;
                </div>
              </div>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
