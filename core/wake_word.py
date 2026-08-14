from __future__ import annotations
import threading
import pvporcupine
import sounddevice as sd
import numpy as np

class WakeWordDetector:
    def __init__(
        self,
        access_key: str,
        keyword: str = "jarvis",
        on_wake: callable = None,
    ):
        self._access_key = access_key
        self._keyword = keyword
        self._on_wake = on_wake
        self._porcupine: pvporcupine.Porcupine | None = None
        self._stream: sd.InputStream | None = None
        self._active = False
        self._paused = False
        self._lock = threading.Lock()

    def start(self):
        with self._lock:
            if self._active:
                return
            try:
                self._porcupine = pvporcupine.create(
                    access_key=self._access_key,
                    keywords=[self._keyword],
                )
                self._stream = sd.InputStream(
                    samplerate=self._porcupine.sample_rate,
                    channels=1,
                    dtype="int16",
                    blocksize=self._porcupine.frame_length,
                    callback=self._callback,
                )
                self._stream.start()
                self._active = True
                print("[WakeWord] Escuchando 'Jarvis'...")
            except Exception as e:
                print(f"[WakeWord] Error al iniciar: {e}")
                self._cleanup()

    def stop(self):
        with self._lock:
            self._cleanup()

    def pause(self):
        with self._lock:
            self._paused = True

    def resume(self):
        with self._lock:
            self._paused = False

    def _callback(self, indata, frames, time_info, status):
        if self._paused:
            return
        audio = np.frombuffer(indata, dtype=np.int16)
        if self._porcupine and self._porcupine.process(audio) >= 0:
            print("[WakeWord] ¡Jarvis detectado!")
            if self._on_wake:
                self._on_wake()

    def _cleanup(self):
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        if self._porcupine:
            self._porcupine.delete()
            self._porcupine = None
        self._active = False
        self._paused = False
