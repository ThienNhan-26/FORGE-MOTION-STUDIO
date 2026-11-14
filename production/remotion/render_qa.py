from __future__ import annotations

import json
import math
import shutil
import statistics
import subprocess
from pathlib import Path
from typing import Any


def _run(command: list[str], *, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, timeout=timeout, check=False)


def _pixel_stats(rgb: bytes, width: int = 160, height: int = 90) -> dict[str, float | int]:
    expected = width * height * 3
    if len(rgb) != expected:
        raise ValueError(f'Expected {expected} RGB bytes, received {len(rgb)}')

    # Rec.601 luma is sufficient for a conservative blank-frame test.
    luma = [
        0.299 * rgb[i] + 0.587 * rgb[i + 1] + 0.114 * rgb[i + 2]
        for i in range(0, len(rgb), 3)
    ]
    low = min(luma)
    high = max(luma)
    stddev = statistics.pstdev(luma)

    # Edge count catches spatial content even when the frame is mostly one color.
    edges = 0
    comparisons = 0
    for y in range(height):
        row = y * width
        for x in range(width):
            idx = row + x
            if x + 1 < width:
                comparisons += 1
                edges += abs(luma[idx] - luma[idx + 1]) >= 8
            if y + 1 < height:
                comparisons += 1
                edges += abs(luma[idx] - luma[idx + width]) >= 8

    return {
        'luma_min': round(low, 2),
        'luma_max': round(high, 2),
        'luma_stddev': round(stddev, 3),
        'edge_density': round(edges / max(1, comparisons), 6),
        'edge_count': edges,
    }


def validate_render_output(output_path: Path, spec: Any) -> dict[str, Any]:
    """Return a JSON-safe report. Pass/fail is based on decodability and visible pixels."""
    report: dict[str, Any] = {
        'passed': False,
        'file': str(output_path),
        'file_size_bytes': output_path.stat().st_size if output_path.is_file() else 0,
        'checks': {},
        'samples': [],
    }

    ffprobe = shutil.which('ffprobe')
    ffmpeg = shutil.which('ffmpeg')
    if not ffprobe or not ffmpeg:
        report['error'] = 'ffprobe and ffmpeg must both be available on PATH.'
        return report
    if not output_path.is_file() or report['file_size_bytes'] < 1024:
        report['error'] = 'MP4 missing or smaller than 1 KiB.'
        return report

    probe = _run([
        ffprobe, '-v', 'error', '-select_streams', 'v:0',
        '-show_entries', 'stream=codec_name,width,height,avg_frame_rate,r_frame_rate,nb_frames',
        '-show_entries', 'format=duration,size', '-of', 'json', str(output_path),
    ])
    if probe.returncode != 0:
        report['error'] = (probe.stderr or probe.stdout or b'ffprobe failed').decode('utf-8', 'replace')[-3000:]
        return report

    try:
        metadata = json.loads(probe.stdout.decode('utf-8'))
        stream = metadata['streams'][0]
        duration = float(metadata['format']['duration'])
        rate_text = stream.get('avg_frame_rate') or stream.get('r_frame_rate') or '0/1'
        numerator, denominator = (int(part) for part in rate_text.split('/', 1))
        actual_fps = numerator / denominator if denominator else 0.0
        actual_width = int(stream['width'])
        actual_height = int(stream['height'])
        raw_frame_count = stream.get('nb_frames')
        frame_count = int(raw_frame_count) if raw_frame_count and str(raw_frame_count).isdigit() else round(duration * actual_fps)
    except (KeyError, IndexError, TypeError, ValueError, ZeroDivisionError) as exc:
        report['error'] = f'Invalid MP4 metadata: {exc}'
        return report

    expected_frames = int(spec.duration_seconds * spec.fps)
    dimensions_ok = actual_width == spec.width and actual_height == spec.height
    fps_ok = abs(actual_fps - spec.fps) <= 0.02
    duration_ok = abs(duration - spec.duration_seconds) <= max(0.20, 2.0 / spec.fps)
    frame_count_ok = abs(frame_count - expected_frames) <= 2
    report['video'] = {
        'codec': stream.get('codec_name'),
        'width': actual_width,
        'height': actual_height,
        'fps': round(actual_fps, 4),
        'duration_seconds': round(duration, 4),
        'frame_count': frame_count,
    }
    report['checks']['dimensions'] = dimensions_ok
    report['checks']['fps'] = fps_ok
    report['checks']['duration'] = duration_ok
    report['checks']['frame_count'] = frame_count_ok
    if not all((dimensions_ok, fps_ok, duration_ok, frame_count_ok)):
        report['error'] = (
            f'Video metadata mismatch: got {actual_width}x{actual_height}@{actual_fps:.3f}fps, '
            f'{duration:.3f}s/{frame_count} frames; expected {spec.width}x{spec.height}@{spec.fps}fps, '
            f'{spec.duration_seconds}s/{expected_frames} frames.'
        )
        return report

    # Sample across the timeline. A nearly flat background-only frame should fail.
    sample_times = sorted(set([
        max(0.0, min(duration - 1.0 / spec.fps, duration * 0.08)),
        duration * 0.50,
        duration * 0.90,
    ]))
    for timestamp in sample_times:
        decoded = _run([
            ffmpeg, '-v', 'error', '-ss', f'{timestamp:.4f}', '-i', str(output_path),
            '-frames:v', '1', '-vf', 'scale=160:90:flags=area,format=rgb24',
            '-f', 'rawvideo', 'pipe:1',
        ])
        if decoded.returncode != 0:
            report['samples'].append({'time_seconds': round(timestamp, 3), 'passed': False, 'error': 'FFmpeg decode failed'})
            continue
        try:
            stats = _pixel_stats(decoded.stdout)
        except ValueError as exc:
            report['samples'].append({'time_seconds': round(timestamp, 3), 'passed': False, 'error': str(exc)})
            continue
        # Thresholds are deliberately lenient for a small object on a large background,
        # but reject a flat solid-color render and its minor codec noise.
        sample_pass = (
            float(stats['luma_stddev']) >= 1.5
            and float(stats['luma_max']) - float(stats['luma_min']) >= 10.0
            and int(stats['edge_count']) >= 35
        )
        report['samples'].append({
            'time_seconds': round(timestamp, 3),
            'passed': sample_pass,
            **stats,
        })

    passed_samples = sum(1 for sample in report['samples'] if sample.get('passed'))
    report['checks']['visible_frame_content'] = passed_samples >= 2
    if passed_samples < 2:
        report['error'] = (
            f'Only {passed_samples}/3 sampled frames contain measurable image structure. '
            'The render may be blank or its 3D scene may not be visible.'
        )
        return report

    report['passed'] = True
    report['summary'] = (
        f"{actual_width}x{actual_height}@{actual_fps:g}fps, {duration:.2f}s, "
        f"{frame_count} frames; {passed_samples}/3 sampled frames contain visible pixel structure."
    )
    return report
