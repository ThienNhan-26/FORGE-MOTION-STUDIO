from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from production.remotion.render_qa import validate_render_output


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'ffmpeg/ffprobe required')
class RenderQATests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.spec = SimpleNamespace(width=320, height=180, fps=30, duration_seconds=2)

    def tearDown(self):
        self.temp.cleanup()

    def _make_video(self, source: str, name: str) -> Path:
        target = self.root / name
        command = [
            'ffmpeg', '-y', '-v', 'error', '-f', 'lavfi', '-i', source,
            '-t', '2', '-r', '30', '-an', '-c:v', 'mpeg4', '-q:v', '3', str(target),
        ]
        subprocess.run(command, check=True, capture_output=True)
        return target

    def test_rejects_solid_background_video(self):
        video = self._make_video('color=c=skyblue:s=320x180:r=30', 'blank.mp4')
        report = validate_render_output(video, self.spec)
        self.assertFalse(report['passed'], report)
        self.assertFalse(report['checks'].get('visible_frame_content', False))

    def test_accepts_pattern_video(self):
        video = self._make_video('testsrc2=size=320x180:rate=30', 'pattern.mp4')
        report = validate_render_output(video, self.spec)
        self.assertTrue(report['passed'], report)
        self.assertTrue(report['checks']['visible_frame_content'])


if __name__ == '__main__':
    unittest.main()
