"""Thinking spinner — Show a spinner while waiting for model response."""

import sys
import threading
import time


class ThinkingSpinner:
    """Animated spinner shown while the model is thinking."""

    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, message: str = "Thinking"):
        self.message = message
        self._running = False
        self._thread = None
        self._frame = 0

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._animate, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=0.3)
        # Clear the spinner line
        sys.stdout.write("\r\x1b[K")
        sys.stdout.flush()

    def _animate(self):
        while self._running:
            frame = self.FRAMES[self._frame % len(self.FRAMES)]
            sys.stdout.write(f"\r\x1b[38;5;208m{frame}\x1b[0m \x1b[90m{self.message}...\x1b[0m")
            sys.stdout.flush()
            self._frame += 1
            time.sleep(0.08)

    def update_message(self, message: str):
        self.message = message
