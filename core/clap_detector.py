import time
import numpy as np


class ClapDetector:
    def __init__(
        self,
        threshold_multiplier: float = 4.0,
        min_rms: float = 2800.0,
        min_zcr: float = 0.075,
        min_hf_ratio: float = 0.32,
        hf_split_hz: float = 1500.0,
        clap_window: float = 1.5,
        clap_cooldown: float = 0.3,
        trigger_cooldown: float = 15.0,
        history_size: int = 50,
        sample_rate: int = 16000,
    ):
        self.threshold_multiplier = threshold_multiplier
        self.min_rms = min_rms
        self.min_zcr = min_zcr
        self.min_hf_ratio = min_hf_ratio
        self.hf_split_hz = hf_split_hz
        self.clap_window = clap_window
        self.clap_cooldown = clap_cooldown
        self.trigger_cooldown = trigger_cooldown
        self.history_size = history_size
        self.sample_rate = sample_rate

        self.last_detected = 0.0
        self.first_clap_time = 0.0
        self.waiting = False
        self.rms_history: list[float] = []
        self._last_trigger = 0.0
        self.callback = None

    def set_callback(self, callback):
        self.callback = callback

    def _spectral_is_clap(self, data: np.ndarray) -> bool:
        x = data.astype(np.float64)
        rms = float(np.sqrt(np.mean(x ** 2)))

        baseline = (
            float(np.mean(self.rms_history))
            if self.rms_history
            else 0.0
        )
        threshold = max(baseline * self.threshold_multiplier, self.min_rms)
        if rms < threshold:
            return False

        zcr = float(np.sum(np.abs(np.diff(np.signbit(x)))) / len(x))
        if zcr < self.min_zcr:
            return False

        fft = np.fft.rfft(x)
        amp = np.abs(fft)
        energy = amp ** 2
        total_energy = float(np.sum(energy)) + 1e-10

        freqs = np.fft.rfftfreq(len(x), d=1.0 / self.sample_rate)
        hf_mask = freqs > self.hf_split_hz
        hf_energy = float(np.sum(energy[hf_mask]))
        hf_ratio = hf_energy / total_energy

        return hf_ratio > self.min_hf_ratio

    def process(self, audio_data: np.ndarray) -> bool:
        now = time.time()
        if now - self._last_trigger < self.trigger_cooldown:
            return False

        try:
            is_clap = self._spectral_is_clap(audio_data)
        except Exception:
            is_clap = False

        # La referencia debe representar solo el ruido ambiente. Incluir el
        # primer aplauso puede multiplicar el umbral y ocultar el segundo.
        if not is_clap:
            rms = float(np.sqrt(np.mean(audio_data.astype(np.float64) ** 2)))
            self.rms_history.append(rms)
            if len(self.rms_history) > self.history_size:
                self.rms_history.pop(0)

        if is_clap and (now - self.last_detected) > self.clap_cooldown:
            self.last_detected = now

            if not self.waiting:
                self.first_clap_time = now
                self.waiting = True
            elif (now - self.first_clap_time) <= self.clap_window:
                self.waiting = False
                self._last_trigger = now
                if self.callback:
                    self.callback()
                return True
            else:
                self.first_clap_time = now

        if self.waiting and (now - self.first_clap_time) > self.clap_window:
            self.waiting = False

        return False

    def reset(self):
        self.last_detected = 0.0
        self.first_clap_time = 0.0
        self.waiting = False
        self.rms_history.clear()
