"""Small, offline bag-of-character-ngrams neural intent classifier.

The released int8 weights are trained from public, authored examples. Audio,
calendar content and calibration phrases never train or leave this device.
"""
from __future__ import annotations

from functools import lru_cache
from importlib.resources import files
import hashlib
import json
import math
import re


FEATURES = 2048


def features(text: str) -> tuple[int, ...]:
    clean = re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]', ' ', text.casefold())).strip()
    words = clean.split()
    grams = set(words)
    grams.update(' '.join(words[i:i+2]) for i in range(len(words)-1))
    grams.update(clean[i:i+3] for i in range(max(0,len(clean)-2)))
    return tuple(sorted({int.from_bytes(hashlib.blake2s(gram.encode(),digest_size=4).digest(),'little') % FEATURES
                         for gram in grams if gram}))


@lru_cache(maxsize=1)
def _model():
    path = files('luma').joinpath('voice_intents.json')
    try:
        data=json.loads(path.read_text(encoding='utf-8'))
    except (FileNotFoundError, ValueError):
        return None
    if data.get('features') != FEATURES or data.get('version') != 1:
        return None
    return data


def predict(text: str) -> tuple[str, float, float] | None:
    data=_model()
    indices=features(text)
    if not data or not indices:
        return None
    # A single learned embedding-bag/softmax layer, with int8 sparse weights.
    scores=[]
    for label in data['labels']:
        weights=data['weights'][label]
        scores.append((data['bias'][label]+sum(weights.get(str(index),0) for index in indices)/math.sqrt(len(indices)))/data['scale'])
    top=sorted(range(len(scores)),key=scores.__getitem__,reverse=True)[:2]
    offset=scores[top[0]]
    exp=[math.exp(max(-80,min(0,score-offset))) for score in scores]
    probability=exp[top[0]]/sum(exp)
    margin=scores[top[0]]-scores[top[1]] if len(top)>1 else 100.0
    return data['labels'][top[0]], probability, margin


def match(text: str, *, confidence: float = .72, margin: float = 1.7) -> str | None:
    result=predict(text)
    return result[0] if result and result[1]>=confidence and result[2]>=margin else None
