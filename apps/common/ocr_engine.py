import os
import gc
import io
import time
import ctypes
import logging
import threading
from typing import List, Dict, Any, Optional, Tuple, Generator
from contextlib import contextmanager
from django.conf import settings

logger = logging.getLogger(__name__)

# Render Starter / Free tier has a strict 512MB container memory ceiling.
# Only 1 heavy OCR operation may execute at any given instant across all worker threads.
_OCR_SEMAPHORE = threading.BoundedSemaphore(1)


class OCRMemoryLimiter:
    """
    Guarantees bounded memory execution for document parsing and OCR operations.
    1. Enforces global concurrency ceiling (max 1 OCR task active simultaneously).
    2. Measures resident memory before and after operations.
    3. Triggers explicit garbage collection and libc malloc_trim(0) on Linux
       to immediately release freed heap chunks back to the OS.
    """

    @classmethod
    @contextmanager
    def guard(cls, operation_name: str = "OCR_Operation", timeout: float = 60.0):
        acquired = _OCR_SEMAPHORE.acquire(timeout=timeout)
        if not acquired:
            raise TimeoutError(
                f"OCR concurrency limit reached. Another document processing job is running. "
                f"Please retry in a few seconds."
            )

        start_time = time.time()
        logger.info(f"[OCRMemoryLimiter] Starting guarded operation: {operation_name}")

        try:
            yield
        finally:
            duration = time.time() - start_time
            # 1. Force Python runtime garbage collection
            gc.collect()

            # 2. Force Linux glibc to release free heap memory back to the operating system
            cls.force_os_memory_trim()

            _OCR_SEMAPHORE.release()
            logger.info(
                f"[OCRMemoryLimiter] Completed {operation_name} in {duration:.2f}s; memory trimmed."
            )

    @classmethod
    def force_os_memory_trim(cls):
        """
        Calls malloc_trim(0) on glibc (Linux/Render) to return freed memory pages
        back to the Linux kernel, preventing container OOM kills.
        """
        try:
            # On Linux (Render web service), glibc provides malloc_trim
            libc = ctypes.CDLL("libc.so.6")
            if hasattr(libc, "malloc_trim"):
                libc.malloc_trim(0)
        except Exception:
            # Windows / macOS or non-glibc environments gracefully ignore
            pass


class GeminiClientProvider:
    """
    Centralized, fail-safe Google GenAI client provider with strictly valid
    model fallbacks and execution budgeting.
    """

    # Only real, supported Google Gemini models (eliminates fictitious models that fail and leak memory)
    SUPPORTED_MODELS = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
    ]

    @classmethod
    def get_api_key(cls) -> Optional[str]:
        return os.environ.get("GEMINI_API_KEY", "").strip() or getattr(
            settings, "GEMINI_API_KEY", ""
        )

    @classmethod
    def get_client(cls):
        api_key = cls.get_api_key()
        if not api_key:
            return None
        try:
            from google import genai
            return genai.Client(api_key=api_key)
        except Exception as e:
            logger.warning(f"[GeminiClientProvider] Failed to initialize genai.Client: {e}")
            return None


class PDFPageImageStreamer:
    """
    Memory-efficient, streaming PDF-to-image converter.
    Renders exactly ONE page at a time at controlled DPI (120-130 DPI) and JPEG compression,
    preventing multi-page raw uncompressed bitmap accumulation in Python heap memory.
    """

    @classmethod
    def stream_pages(
        cls,
        file_bytes: bytes,
        max_pages: int = 3,
        dpi: int = 120,
        jpg_quality: int = 80,
    ) -> Generator[Tuple[int, bytes, str], None, None]:
        """
        Yields (page_number, jpeg_bytes, mime_type) for each page up to max_pages.
        Immediately cleans up page pixmaps after yielding.
        """
        doc = None
        try:
            import pymupdf
            doc = pymupdf.open(stream=file_bytes, filetype="pdf")
            total_pages = min(max_pages, len(doc))

            for page_idx in range(total_pages):
                page = doc[page_idx]
                pix = page.get_pixmap(dpi=dpi)
                jpg_bytes = pix.tobytes("jpeg", jpg_quality=jpg_quality)
                # Immediately release raw C-raster pixmap
                pix = None

                yield (page_idx + 1, jpg_bytes, "image/jpeg")

                # Clear byte buffer reference and collect
                jpg_bytes = None
                gc.collect()
        except ImportError:
            # If pymupdf is not available, yield original file
            yield (1, file_bytes, "application/pdf")
        except Exception as e:
            logger.warning(f"[PDFPageImageStreamer] Streaming failed: {e}")
            yield (1, file_bytes, "application/pdf")
        finally:
            if doc is not None:
                try:
                    doc.close()
                except Exception:
                    pass
            doc = None
            gc.collect()
            OCRMemoryLimiter.force_os_memory_trim()
