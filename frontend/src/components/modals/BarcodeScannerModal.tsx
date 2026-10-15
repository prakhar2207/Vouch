"use client";

import React, { useEffect, useRef, useState, useCallback } from "react";
import { 
  Camera, 
  X, 
  RefreshCw, 
  Flashlight, 
  FlashlightOff, 
  CheckCircle2, 
  AlertCircle, 
  Barcode, 
  Keyboard, 
  Volume2, 
  VolumeX 
} from "lucide-react";
import { Html5Qrcode, Html5QrcodeSupportedFormats } from "html5-qrcode";

interface BarcodeScannerModalProps {
  isOpen: boolean;
  onClose: () => void;
  onScan: (barcode: string) => void;
  title?: string;
  continuous?: boolean;
}

export default function BarcodeScannerModal({
  isOpen,
  onClose,
  onScan,
  title = "Scan Item Barcode / QR",
  continuous = true,
}: BarcodeScannerModalProps) {
  const [cameras, setCameras] = useState<Array<{ id: string; label: string }>>([]);
  const [selectedCameraId, setSelectedCameraId] = useState<string>("");
  const [isScanning, setIsScanning] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [lastScanned, setLastScanned] = useState<{ code: string; time: number } | null>(null);
  const [scanCount, setScanCount] = useState<number>(0);
  const [torchOn, setTorchOn] = useState(false);
  const [hasTorch, setHasTorch] = useState(false);
  const [soundEnabled, setSoundEnabled] = useState(true);
  const [manualCode, setManualCode] = useState("");
  const [isContinuous, setIsContinuous] = useState(continuous);

  const scannerRef = useRef<Html5Qrcode | null>(null);
  const lastScannedCodeRef = useRef<{ code: string; time: number } | null>(null);
  const containerId = "barcode-scanner-viewfinder";

  // Web Audio API POS Beep
  const playBeep = useCallback(() => {
    if (!soundEnabled) return;
    try {
      const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      if (!AudioCtx) return;
      const ctx = new AudioCtx();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(1400, ctx.currentTime);
      gain.gain.setValueAtTime(0.18, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.12);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.12);
    } catch {
      // AudioContext unavailable or blocked
    }
  }, [soundEnabled]);

  const handleScanSuccess = useCallback(
    (decodedText: string) => {
      const trimmed = decodedText.trim();
      if (!trimmed) return;

      const now = Date.now();
      const last = lastScannedCodeRef.current;
      // Debounce identical scans within 1.2s to prevent multiple triggers per single barcode
      if (last && last.code === trimmed && now - last.time < 1200) {
        return;
      }

      lastScannedCodeRef.current = { code: trimmed, time: now };
      setLastScanned({ code: trimmed, time: now });
      setScanCount((prev) => prev + 1);

      playBeep();
      if (typeof navigator !== "undefined" && navigator.vibrate) {
        try {
          navigator.vibrate(80);
        } catch {
          // Ignore vibration error
        }
      }

      onScan(trimmed);

      if (!isContinuous) {
        onClose();
      }
    },
    [isContinuous, onScan, onClose, playBeep]
  );

  // Initialize camera list
  useEffect(() => {
    if (!isOpen) return;

    let mounted = true;

    Html5Qrcode.getCameras()
      .then((devices) => {
        if (!mounted) return;
        if (devices && devices.length > 0) {
          const formatted = devices.map((d) => ({
            id: d.id,
            label: d.label || `Camera ${d.id.substring(0, 5)}`,
          }));
          setCameras(formatted);

          // Find back / environment camera if available
          const backCam = formatted.find(
            (c) =>
              c.label.toLowerCase().includes("back") ||
              c.label.toLowerCase().includes("rear") ||
              c.label.toLowerCase().includes("environment")
          );
          setSelectedCameraId(backCam ? backCam.id : formatted[0].id);
        } else {
          // No camera devices returned explicitly, fallback to facingMode: environment
          setSelectedCameraId("environment");
        }
      })
      .catch((err) => {
        console.warn("Could not enumerate camera devices:", err);
        // Fallback to environment facingMode
        if (mounted) {
          setSelectedCameraId("environment");
        }
      });

    return () => {
      mounted = false;
    };
  }, [isOpen]);

  // Start scanner when camera is selected
  useEffect(() => {
    if (!isOpen || !selectedCameraId) return;

    let active = true;
    const scanner = new Html5Qrcode(containerId, {
      formatsToSupport: [
        Html5QrcodeSupportedFormats.EAN_13,
        Html5QrcodeSupportedFormats.EAN_8,
        Html5QrcodeSupportedFormats.CODE_128,
        Html5QrcodeSupportedFormats.CODE_39,
        Html5QrcodeSupportedFormats.CODE_93,
        Html5QrcodeSupportedFormats.UPC_A,
        Html5QrcodeSupportedFormats.UPC_E,
        Html5QrcodeSupportedFormats.UPC_EAN_EXTENSION,
        Html5QrcodeSupportedFormats.QR_CODE,
        Html5QrcodeSupportedFormats.ITF,
        Html5QrcodeSupportedFormats.DATA_MATRIX,
      ],
      verbose: false,
    });
    scannerRef.current = scanner;

    const cameraConfig =
      selectedCameraId === "environment"
        ? { facingMode: "environment" }
        : selectedCameraId;

    scanner
      .start(
        cameraConfig,
        {
          fps: 15,
          qrbox: (viewfinderWidth, viewfinderHeight) => {
            const width = Math.floor(Math.min(viewfinderWidth * 0.88, 320));
            const height = Math.floor(Math.min(viewfinderHeight * 0.55, 180));
            return { width: Math.max(width, 220), height: Math.max(height, 120) };
          },
          aspectRatio: 1.6,
        },
        (decodedText) => {
          if (active) {
            handleScanSuccess(decodedText);
          }
        },
        () => {
          // Frame-by-frame parse failure is expected when no barcode is in frame
        }
      )
      .then(() => {
        if (!active) {
          scanner.stop().then(() => scanner.clear()).catch(() => {});
          return;
        }
        setIsScanning(true);
        setErrorMessage(null);

        // Check torch capability
        try {
          const capabilities = scanner.getRunningTrackCapabilities();
          if (capabilities && (capabilities as unknown as { torch?: boolean }).torch) {
            setHasTorch(true);
          } else {
            setHasTorch(false);
          }
        } catch {
          setHasTorch(false);
        }
      })
      .catch((err) => {
        if (!active) return;
        console.error("Failed to start camera scanner:", err);
        setErrorMessage(
          err?.name === "NotAllowedError" || String(err).includes("Permission")
            ? "Camera permission was denied. Please allow camera access in your browser or phone settings."
            : "Could not access camera. Please make sure no other app is using it."
        );
        setIsScanning(false);
      });

    return () => {
      active = false;
      if (scanner.isScanning) {
        scanner
          .stop()
          .then(() => {
            scanner.clear();
          })
          .catch((err) => {
            console.warn("Error stopping scanner on cleanup:", err);
          });
      }
    };
  }, [isOpen, selectedCameraId, handleScanSuccess]);

  // Toggle Torch
  const toggleTorch = async () => {
    if (!scannerRef.current || !hasTorch) return;
    try {
      const nextTorch = !torchOn;
      await scannerRef.current.applyVideoConstraints({
        advanced: [{ torch: nextTorch } as MediaTrackConstraintSet],
      });
      setTorchOn(nextTorch);
    } catch (e) {
      console.warn("Torch toggle failed:", e);
    }
  };

  // Switch Camera
  const switchCamera = () => {
    if (cameras.length <= 1) return;
    const currentIndex = cameras.findIndex((c) => c.id === selectedCameraId);
    const nextIndex = (currentIndex + 1) % cameras.length;
    setSelectedCameraId(cameras[nextIndex].id);
  };

  // Handle Manual Submit
  const handleManualSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const code = manualCode.trim();
    if (!code) return;
    handleScanSuccess(code);
    setManualCode("");
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="relative w-full max-w-lg bg-card border border-border rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[92vh]">
        {/* Modal Header */}
        <div className="px-4 py-3 bg-muted/60 border-b border-border flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center">
              <Camera className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-foreground">{title}</h3>
              <p className="text-[11px] text-muted-foreground">
                {isContinuous ? "Continuous Scan Mode Active" : "Point camera at barcode"}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-1">
            {/* Sound Toggle */}
            <button
              type="button"
              onClick={() => setSoundEnabled(!soundEnabled)}
              className={`p-2 rounded-lg transition-colors ${
                soundEnabled ? "text-primary hover:bg-primary/10" : "text-muted-foreground hover:bg-muted"
              }`}
              title={soundEnabled ? "Sound Beep: On" : "Sound Beep: Off"}
            >
              {soundEnabled ? <Volume2 className="w-4 h-4" /> : <VolumeX className="w-4 h-4" />}
            </button>

            {/* Torch Toggle */}
            {hasTorch && (
              <button
                type="button"
                onClick={toggleTorch}
                className={`p-2 rounded-lg transition-colors ${
                  torchOn ? "text-amber-500 bg-amber-500/10" : "text-muted-foreground hover:bg-muted"
                }`}
                title="Toggle Torch/Flashlight"
              >
                {torchOn ? <Flashlight className="w-4 h-4" /> : <FlashlightOff className="w-4 h-4" />}
              </button>
            )}

            {/* Switch Camera */}
            {cameras.length > 1 && (
              <button
                type="button"
                onClick={switchCamera}
                className="p-2 text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg transition-colors"
                title="Switch Camera (Front / Back)"
              >
                <RefreshCw className="w-4 h-4" />
              </button>
            )}

            {/* Close Button */}
            <button
              type="button"
              onClick={onClose}
              className="p-2 text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg transition-colors ml-1"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Viewfinder Area */}
        <div className="relative flex-1 bg-black min-h-[260px] sm:min-h-[320px] flex items-center justify-center overflow-hidden">
          {/* HTML5 QR Code Container */}
          <div
            id={containerId}
            className="w-full h-full [&_video]:object-cover [&_video]:w-full [&_video]:h-full"
          />

          {/* Laser Target Scan Overlay */}
          {isScanning && (
            <div className="absolute inset-0 pointer-events-none flex flex-col items-center justify-center p-6">
              <div className="relative w-full max-w-[320px] h-36 border-2 border-primary/70 rounded-xl shadow-[0_0_20px_rgba(59,130,246,0.3)] flex items-center justify-center overflow-hidden">
                {/* Red Laser Sweep */}
                <div className="absolute w-full h-0.5 bg-red-500/80 shadow-[0_0_8px_#ef4444] animate-pulse top-1/2 -translate-y-1/2" />
                {/* Corner Accents */}
                <div className="absolute top-1 left-1 w-3 h-3 border-t-2 border-l-2 border-primary" />
                <div className="absolute top-1 right-1 w-3 h-3 border-t-2 border-r-2 border-primary" />
                <div className="absolute bottom-1 left-1 w-3 h-3 border-b-2 border-l-2 border-primary" />
                <div className="absolute bottom-1 right-1 w-3 h-3 border-b-2 border-r-2 border-primary" />
              </div>
              <p className="text-[12px] font-medium text-white/90 drop-shadow mt-3 bg-black/50 px-3 py-1 rounded-full border border-white/20">
                Align barcode within frame
              </p>
            </div>
          )}

          {/* Error Message */}
          {errorMessage && (
            <div className="absolute inset-4 z-10 flex flex-col items-center justify-center text-center p-6 bg-card/95 backdrop-blur-md rounded-xl border border-destructive/30">
              <AlertCircle className="w-10 h-10 text-destructive mb-3" />
              <p className="text-sm font-semibold text-foreground mb-1">Camera Access Issue</p>
              <p className="text-xs text-muted-foreground mb-4 max-w-sm">{errorMessage}</p>
              <button
                type="button"
                onClick={() => {
                  setErrorMessage(null);
                  setSelectedCameraId("environment");
                }}
                className="px-4 py-2 bg-primary text-primary-foreground text-xs font-semibold rounded-lg hover:bg-primary/90 transition-all cursor-pointer"
              >
                Retry Camera
              </button>
            </div>
          )}

          {/* Last Scanned Banner */}
          {lastScanned && Date.now() - lastScanned.time < 2500 && (
            <div className="absolute top-4 left-4 right-4 z-20 flex items-center justify-between gap-2 p-3 bg-emerald-600/95 text-white rounded-xl shadow-lg border border-emerald-400/40 backdrop-blur-md animate-in slide-in-from-top duration-200">
              <div className="flex items-center gap-2 overflow-hidden">
                <CheckCircle2 className="w-5 h-5 text-emerald-200 shrink-0" />
                <div className="truncate">
                  <div className="text-[11px] font-medium text-emerald-100 uppercase tracking-wider">
                    Scanned Successfully
                  </div>
                  <div className="text-xs font-mono font-bold truncate">
                    {lastScanned.code}
                  </div>
                </div>
              </div>
              <div className="text-right shrink-0">
                <span className="text-[10px] bg-emerald-700/80 px-2 py-0.5 rounded-full font-mono">
                  #{scanCount}
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Modal Controls & Fallback Input */}
        <div className="p-3 bg-card border-t border-border space-y-3">
          {/* Continuous Scan Toggle & Count */}
          <div className="flex items-center justify-between text-xs">
            <label className="flex items-center gap-2 cursor-pointer select-none text-muted-foreground hover:text-foreground">
              <input
                type="checkbox"
                checked={isContinuous}
                onChange={(e) => setIsContinuous(e.target.checked)}
                className="rounded border-input text-primary focus:ring-primary w-4 h-4 cursor-pointer"
              />
              <span className="font-medium">Continuous Scan (Keep Camera Open)</span>
            </label>

            {scanCount > 0 && (
              <span className="text-[11px] font-semibold text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-md border border-emerald-500/20 font-mono">
                {scanCount} {scanCount === 1 ? "item" : "items"} scanned
              </span>
            )}
          </div>

          {/* Manual Input Fallback */}
          <form onSubmit={handleManualSubmit} className="flex items-center gap-2">
            <div className="relative flex-1">
              <Barcode className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
              <input
                type="text"
                value={manualCode}
                onChange={(e) => setManualCode(e.target.value)}
                placeholder="Can't scan? Type Barcode/SKU & press Add..."
                className="w-full pl-9 pr-3 py-1.5 bg-muted/50 border border-input rounded-lg text-xs font-mono placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:bg-background transition-all"
              />
            </div>
            <button
              type="submit"
              disabled={!manualCode.trim()}
              className="px-3 py-1.5 bg-muted hover:bg-muted/80 text-foreground border border-input rounded-lg text-xs font-semibold disabled:opacity-40 transition-all flex items-center gap-1 shrink-0 cursor-pointer"
            >
              <Keyboard className="w-3.5 h-3.5" />
              <span>Add</span>
            </button>
          </form>

          {/* Footer Close / Done */}
          <div className="flex items-center justify-between pt-1 border-t border-border/50">
            <span className="text-[11px] text-muted-foreground">
              Supports: 1D Barcodes, EAN, UPC, Code 128 & QR Codes
            </span>
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-1.5 bg-primary text-primary-foreground text-xs font-semibold rounded-lg hover:bg-primary/90 transition-all cursor-pointer shadow-sm"
            >
              Done Scanning
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
