"""Protocol integrity tests; never call external models."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

PATH=Path(__file__).resolve().parents[1]/'scripts/innovation1/four_group_pipeline.py'
spec=importlib.util.spec_from_file_location('four',PATH); m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class FourGroupTests(unittest.TestCase):
    def test_cross_frame_conflict_and_uncertainty(self):
        self.assertEqual(m.merge_answers(['Yes','No']),'Uncertain')
        self.assertEqual(m.merge_answers(['Uncertain','Uncertain']),'Uncertain')
        self.assertEqual(m.merge_answers(['Yes','Uncertain']),'Yes')
        self.assertEqual(m.merge_answers(['No','Uncertain']),'No')
        with self.assertRaises(ValueError):m.merge_answers(['Maybe'])

    def test_unfrozen_and_changed_description_blocked(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(m,'ROOT',Path(tmp)):
            p=Path(tmp)/'prompt.txt';p.write_text('描述')
            d={'file':'prompt.txt','status':'pending','version':'v1','reviewer':'person','sha256':m.digest(p)}
            t={'descriptions':{'G1':d}}
            self.assertFalse(m.description_ok(t,'G1'))
            d['status']='frozen';self.assertTrue(m.description_ok(t,'G1'))
            p.write_text('变更');self.assertFalse(m.description_ok(t,'G1'))

    def test_manifest_matches_current_single_generation_batch(self):
        x=m.protocol();vs=m.read(m.RUN/'generation_manifest.json')
        self.assertEqual(len(vs),20)
        self.assertEqual(set(v['group'] for v in vs),set(m.GROUPS))
        self.assertEqual(x['planned_tasks'],5)
        self.assertEqual(x['repeats'],1)
        self.assertEqual(x['completed_videos'],20)
        self.assertEqual(x['formally_verified_videos'],0)
        self.assertTrue(all(v['video_sha256'] for v in vs))
        self.assertTrue(all(v['provenance_status']=='received_pending_input_and_model_config_verification' for v in vs))

    def test_temporal_questions_are_not_sent_to_keyframe_evaluator(self):
        x=m.protocol()
        questions=[q for t in x['tasks'] for q in t['questions']]
        self.assertEqual(len(questions),20)
        temporal={q['fact_id'] for q in questions if q['evidence_mode']=='continuous_video'}
        self.assertEqual(temporal,{'T06-F3','T07-F3','T07-F4'})
        jobs=m.read(m.RUN/'evaluation_requests.json')
        self.assertTrue(all(not temporal.intersection(job['question_ids']) for job in jobs))
        temporal_jobs=m.read(m.RUN/'temporal_evaluation_requests.json')
        self.assertEqual({fid for job in temporal_jobs for fid in job['question_ids']},temporal)

    def test_reference_requires_human_and_visual_yes(self):
        e={'video_sha256':'abc'}
        q={'status':'confirmed','reviewer':'reviewer','reference_answer':'Uncertain','required':True,'source_evidence_sha256':m.stable(e),'evidence_mode':'keyframes'}
        with patch.object(m,'evidence',return_value=e):
            self.assertFalse(m.reference_ok({'questions':[q]}))
            q['required']=False;self.assertTrue(m.reference_ok({'questions':[q]}))
            q['reviewer']=None;self.assertFalse(m.reference_ok({'questions':[q]}))

    def test_real_ffmpeg_timestamp_extraction(self):
        import subprocess
        with tempfile.TemporaryDirectory() as tmp, patch.object(m,'ROOT',Path(tmp)):
            video=Path(tmp)/'sample.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=64x64:r=10:d=1','-c:v','mpeg4',str(video)],check=True)
            result=m.extract(video,Path(tmp)/'frames',[0.25,0.75])
            self.assertEqual(len(result['frames']),2)
            for f in result['frames']:
                self.assertLessEqual(abs(f['actual_sec']-f['requested_sec']),0.051)
                self.assertTrue((Path(tmp)/f['frame_file']).is_file())

    def test_summary_requires_complete_repeats_and_keeps_uncertain_denominator(self):
        import copy
        x=copy.deepcopy(m.protocol()); t=x['tasks'][0]
        for q in t['questions']:
            q.update(required=True,reference_answer='Yes')
        videos=[];jobs=[]
        with tempfile.TemporaryDirectory() as tmp, patch.object(m,'RUN',Path(tmp)), patch.object(m,'protocol',return_value=x), patch.object(m,'admitted',return_value=True), patch.object(m,'reference_ok',return_value=True):
            x['repeats']=1
            for g in m.GROUPS:
                for r in range(1,2):
                    vid=f"{t['task_id']}_{g}_r{r:02}"
                    videos.append({'video_id':vid,'task_id':t['task_id'],'group':g,'repeat':r})
                    j={'id':vid,'video_id':vid,'task_id':t['task_id']};jobs.append(j)
                    answers={q['fact_id']:{'answer':'Uncertain'} for q in t['questions']}
                    answers[t['questions'][0]['fact_id']]['answer']='Yes'
                    m.write(Path(tmp)/'machine'/f'{vid}.json',{'request':j,'parse_ok':True,'parsed':{'facts':answers,'overall_form':'Uncertain'}})
            m.write(Path(tmp)/'generation_manifest.json',videos);m.write(Path(tmp)/'evaluation_requests.json',jobs)
            m.summarize(); out=m.read(Path(tmp)/'summary.json')
            self.assertEqual(out['status'],'incomplete_not_final')
            self.assertEqual(out['groups']['G1']['cultural_visual_fact_rate'],1/len(t['questions']))
            self.assertEqual(out['groups']['G1']['overall_form_distribution']['Uncertain'],1)

if __name__=='__main__':unittest.main()
