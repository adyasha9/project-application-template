import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from contributor_activity_exports import export_report, versioned_export_paths


class NumberedReportTests(unittest.TestCase):
    def test_repeated_exports_preserve_matching_pairs(self):
        with TemporaryDirectory() as d:
            root=Path(d); previous={}
            with patch('contributor_activity_exports._csv_bytes',return_value=b'csv'),patch('contributor_activity_exports._png_bytes',return_value=b'png'):
                for count in (1,2,3):
                    written=export_report({},csv_path=root/'activity.csv',png_path=root/'activity.png')
                    suffix='' if count==1 else f'_{count}'
                    self.assertEqual([Path(p).name for p in written],[f'activity{suffix}.csv',f'activity{suffix}.png'])
                    for name,digest in previous.items():self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(),digest)
                    previous.update({Path(p).name:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in written})
    def test_half_occupied_pair_skips_entire_number(self):
        with TemporaryDirectory() as d:
            root=Path(d)
            for name in ('activity.csv','activity_2.png'):(root/name).write_text('keep')
            pair=versioned_export_paths(root/'activity.csv',root/'activity.png')
            self.assertEqual([p.name for p in pair],['activity_3.csv','activity_3.png'])
            self.assertEqual((root/'activity.csv').read_text(),'keep')
            self.assertEqual((root/'activity_2.png').read_text(),'keep')
    def test_csv_only_png_only_and_disabled(self):
        with TemporaryDirectory() as d:
            root=Path(d); csv=root/'activity.csv'; png=root/'activity.png'
            csv.write_text('keep');png.write_text('keep')
            self.assertEqual(versioned_export_paths(csv,None),(root/'activity_2.csv',None))
            self.assertEqual(versioned_export_paths(None,png),(None,root/'activity_2.png'))
            self.assertEqual(versioned_export_paths(None,None),(None,None))
    def test_render_failure_creates_nothing(self):
        with TemporaryDirectory() as d:
            root=Path(d);csv=root/'activity.csv';csv.write_text('keep')
            with patch('contributor_activity_exports._csv_bytes',return_value=b'new'),patch('contributor_activity_exports._png_bytes',side_effect=RuntimeError('render failed')):
                with self.assertRaises(RuntimeError):export_report({},csv_path=csv,png_path=root/'activity.png')
            self.assertEqual([p.name for p in root.iterdir()],['activity.csv'])
            self.assertEqual(csv.read_text(),'keep')
    def test_invalid_destinations(self):
        with TemporaryDirectory() as d:
            root=Path(d)
            with self.assertRaises(ValueError):versioned_export_paths(root/'same',root/'same')
            with self.assertRaises(IsADirectoryError):versioned_export_paths(root,None)
            with self.assertRaises(FileNotFoundError):versioned_export_paths(root/'missing'/'out.csv',None)
    def test_dangling_symlink_is_preserved(self):
        with TemporaryDirectory() as d:
            root=Path(d); csv=root/'activity.csv';csv.symlink_to(root/'missing')
            self.assertEqual(versioned_export_paths(csv,None)[0].name,'activity_2.csv')
            self.assertTrue(csv.is_symlink())
    def test_feature_two_two_runs_real_csv_and_png(self):
        repo=Path(__file__).resolve().parents[1]
        with TemporaryDirectory() as d:
            root=Path(d);source=root/'input.json'
            source.write_text(json.dumps([{'number':1,'state':'open','creator':'author','created_date':'2024-01-01T00:00:00Z','updated_date':'2024-01-03T00:00:00Z','events':[]}]))
            command=[sys.executable,str(repo/'run.py'),'--feature','2','--data',str(source),'--output-dir',str(root)]
            previous={}
            for count in (1,2):
                process=subprocess.run(command,cwd=repo,capture_output=True,text=True,timeout=120)
                self.assertEqual(process.returncode,0,process.stderr)
                suffix='' if count==1 else f'_{count}'
                csv=root/f'contributor_activity{suffix}.csv';png=root/f'contributor_activity{suffix}.png'
                self.assertIn('login',csv.read_text(encoding='utf-8-sig'))
                self.assertTrue(png.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'))
                for path,digest in previous.items():self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),digest)
                previous.update({p:hashlib.sha256(p.read_bytes()).hexdigest() for p in (csv,png)})

if __name__=='__main__':unittest.main()
