"""Selected detector lifecycle, with only installer-owned executable paths.

No downloads, sensitivity fallback, phone authorization or command dispatch.
Preparation returns a boundary flag: queued PCM must be discarded before a
newly warmed detector is used. A model being repaired cannot hear commands.
"""
from pathlib import Path

from . import keyword_asset
from .keyword_process import IsolatedKeywordVerifier
from .keyword_wake import KeywordWakeError


class LiveKeywordRuntime:
    def __init__(self, root=keyword_asset.ASSET_ROOT):
        self.root = Path(root)
        self.verifier = None
        self.phase = 'inactive'
        self.error = None

    def close(self):
        if self.verifier is not None:
            self.verifier.close()
            self.verifier = None
        self.phase = 'inactive'
        self.error = None

    def synchronize(self, mode, *, installing=False, suspended=False):
        before = (self.phase, self.verifier)
        if mode != 'acoustic' or suspended or installing:
            self.close()
            if mode == 'acoustic':
                self.phase = 'suspended' if suspended else 'preparing_asset'
            return before != (self.phase, self.verifier)
        if not keyword_asset.ready(self.root):
            self.close()
            self.phase = 'waiting_asset'
            self.error = 'keyword_model_unavailable'
            return before != (self.phase, self.verifier)
        if self.verifier is None:
            folder = self.root / keyword_asset.KEYWORD_ID
            self.verifier = IsolatedKeywordVerifier(folder/'venv/bin/python', folder/'model')
        try:
            started = self.verifier.prepare()
            self.phase, self.error = 'ready', None
            return started or before != (self.phase, self.verifier)
        except KeywordWakeError as error:
            self.phase, self.error = 'failed', str(error)
            return before != (self.phase, self.verifier)

    def report_error(self, code):
        # Rejection of speech is not a failed model. Protocol/runtime failures
        # disable acceptance until synchronize can prepare a healthy worker.
        if code in {'keyword_prefix_rejected', 'keyword_negation_overlap', 'keyword_audio_invalid'}:
            return
        self.phase, self.error = 'failed', code

    def public(self, mode):
        return {'mode': mode, 'phase': self.phase, 'error': self.error}
