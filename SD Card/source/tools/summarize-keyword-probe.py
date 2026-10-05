#!/usr/bin/env python3
"""Print bounded research summaries, not audio or transcript contents."""
import json
from collections import Counter
from pathlib import Path
import sys


def summarize(path):
    if path.stat().st_size > 10*1024*1024:
        raise ValueError('Research report exceeds size limit.')
    report = json.loads(path.read_text())
    rows = report['samples']
    if not isinstance(rows, list) or len(rows) > 10000:
        raise ValueError('Invalid research sample count.')
    totals = {'positive_total': sum(row['expected'] for row in rows),
              'negative_total': sum(not row['expected'] for row in rows),
              'positive_hits': sum(row['expected'] and row['detected'] for row in rows),
              'negative_hits': sum(not row['expected'] and row['detected'] for row in rows)}
    if any(report[name] != value for name, value in totals.items()):
        raise ValueError('Report totals do not match sample evidence.')
    failures = [{'sample': row['sample'], 'expected': row['expected'],
                 'seconds': row['seconds'], 'hits': row['hits']}
                for row in rows if row['expected'] != row['detected']]
    summary = {key: report.get(key) for key in (
        'threshold', 'score', 'max_active_paths', 'contrast_luna', 'contrast_common',
        'contrast_near_names','heldout_phrases','validation_phrases','near_speech_start',
        'candidate_adapter', 'load_ms', 'peak_rss_kib')}
    summary.update(totals)
    summary['hours'] = round(sum(row['seconds'] for row in rows)/3600, 3)
    summary['failures'] = failures[:30]
    summary['failure_count'] = len(failures)
    target_gaps = []
    for row in rows:
        for hit in row['hits']:
            times = hit['timestamps']
            if hit['keyword'] == 'HEY_LUMA' and len(times) == 6:
                target_gaps.append({'sample':row['sample'], 'expected':row['expected'],
                    'name_max_gap':round(max(b-a for a,b in zip(times[2:],times[3:])),3)})
    summary['largest_positive_name_gaps'] = sorted(
        (row for row in target_gaps if row['expected']),
        key=lambda row:row['name_max_gap'], reverse=True)[:5]
    summary['negative_name_gaps'] = [row for row in target_gaps if not row['expected']][:30]
    if any('adapter_detected' in row for row in rows):
        summary['adapter_disagreements'] = sum(row.get('adapter_detected') != row['detected']
                                              for row in rows if 'adapter_detected' in row)
        errors = [row for row in rows if 'adapter_error' in row]
        summary['adapter_error_count'] = len(errors)
        summary['adapter_error_codes'] = dict(Counter(row['adapter_error'] for row in errors))
        summary['adapter_errors'] = [row['sample'] for row in errors[:30]]
    if any('combined_detected' in row for row in rows):
        summary['combined_positive_hits'] = sum(row['expected'] and row.get('combined_detected', False) for row in rows)
        summary['combined_negative_hits'] = sum(not row['expected'] and row.get('combined_detected', False) for row in rows)
    if any('start_gate_detected' in row or 'start_gate_error' in row for row in rows):
        summary['start_gate_positive_hits'] = sum(row['expected'] and row.get('start_gate_detected',False) for row in rows)
        summary['start_gate_negative_hits'] = sum(not row['expected'] and row.get('start_gate_detected',False) for row in rows)
        summary['start_gate_errors'] = sum('start_gate_error' in row for row in rows)
        summary['start_gate_valid_negatives'] = sum(not row['expected'] and 'start_gate_detected' in row for row in rows)
        summary['start_gate_valid_negative_hours'] = round(sum(
            row['seconds'] for row in rows
            if not row['expected'] and 'start_gate_detected' in row)/3600, 3)
    print(path.name, json.dumps(summary, sort_keys=True))


if __name__ == '__main__':
    for argument in sys.argv[1:]:
        summarize(Path(argument))
