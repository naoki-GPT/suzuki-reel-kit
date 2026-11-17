"""APIへ接続せず、二重発注防止・復旧・予算制限を確認する。"""
from pathlib import Path
import json,sys,tempfile,unittest
from unittest.mock import patch,MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
import run
from lib.common import H3Error

class Recovery(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.r=Path(self.tmp.name);(self.r/'project').mkdir()
        self.seg={'id':'a','seconds':5,'target_seconds':5};self.est={'total_jpy':100}
        self.spec={'resolution':'768P','ratio':'9:16','max_run_jpy':500}
        self.state={'fingerprint':'same','segments':{},'status':'prepared'};self.write()
        self.stack=__import__('contextlib').ExitStack()
        self.stack.enter_context(patch.object(run,'fingerprint',return_value='same'))
        self.stack.enter_context(patch.object(run,'inspect_project',return_value=(self.spec,[(self.seg,'prompt',MagicMock(),self.est)],1)))
        self.stack.enter_context(patch.object(run.cost,'check_daily_limit',return_value=(True,'within limit')))
        self.ledger=self.stack.enter_context(patch.object(run.cost,'append_ledger'))
        self.stack.enter_context(patch.object(run.upload,'upload_all'))
        self.stack.enter_context(patch.object(run.client,'build_payload',return_value={}))
        self.post=self.stack.enter_context(patch.object(run.client,'create_task',return_value='fake-task'))
        self.get=self.stack.enter_context(patch.object(run,'retrieve',return_value={'status':'completed','task_id':'fake-task'}))
        self.stack.enter_context(patch.object(run,'render'))
    def write(self):run.save(self.r/'state.json',self.state)
    def tearDown(self):self.stack.close();self.tmp.cleanup()
    def test_new_submits_once_and_records_before_wait(self):
        def waiting(*args):
            state=run.read(self.r/'state.json');self.assertEqual(state['segments']['a']['task_id'],'fake-task')
            return {'status':'completed','task_id':'fake-task'}
        self.get.side_effect=waiting;run.generate(self.r);self.post.assert_called_once();self.ledger.assert_called_once()
    def test_known_order_resumes_without_post(self):
        self.state['segments']['a']={'status':'ordered','task_id':'existing'};self.write();run.generate(self.r)
        self.post.assert_not_called();self.assertEqual(self.get.call_args.args[0],'existing')
    def test_unknown_submission_never_resends(self):
        self.state['segments']['a']={'status':'submitting'};self.write()
        with self.assertRaises(H3Error):run.generate(self.r)
        self.post.assert_not_called()
    def test_network_error_keeps_unknown_state(self):
        self.post.side_effect=H3Error('network error')
        with self.assertRaises(H3Error):run.generate(self.r)
        self.assertEqual(run.read(self.r/'state.json')['segments']['a']['status'],'submitting')
    def test_balance_rejection_is_not_created(self):
        self.post.side_effect=H3Error('HTTP 402 insufficient balance')
        with self.assertRaises(H3Error):run.generate(self.r)
        self.assertEqual(run.read(self.r/'state.json')['segments']['a']['status'],'rejected');self.ledger.assert_not_called()
    def test_total_budget_checked_before_first_order(self):
        self.spec['max_run_jpy']=50
        with self.assertRaises(H3Error):run.generate(self.r)
        self.post.assert_not_called()
    def test_daily_limit_checked_before_first_order(self):
        with patch.object(run.cost,'check_daily_limit',return_value=(False,'limit')):
            with self.assertRaises(H3Error):run.generate(self.r)
        self.post.assert_not_called()
    def test_changed_inputs_block_resume(self):
        self.state['fingerprint']='old';self.write()
        with self.assertRaises(H3Error):run.generate(self.r)
        self.post.assert_not_called()
    def test_complete_segment_not_ordered_again(self):
        (self.r/'work').mkdir();(self.r/'work/raw-a.mp4').write_bytes(b'existing')
        self.state['segments']['a']={'status':'completed','task_id':'existing'};self.write();run.generate(self.r)
        self.post.assert_not_called();self.get.assert_not_called()
    def test_path_escape_rejected(self):
        outside=self.r/'secret.txt';outside.write_text('not a credential')
        with self.assertRaises(H3Error):run.local(self.r/'project','../secret.txt')
    def test_missing_ledger_reservation_recovered(self):
        self.state['segments']['a']={'status':'ordered','task_id':'existing','estimated_jpy':100,'ordered_date':'2026-11-13'};self.write()
        run.generate(self.r)
        self.assertEqual(self.ledger.call_args.args[0]['est_jpy'],100)
        self.assertEqual(self.ledger.call_args.args[0]['date'],'2026-11-13')
        self.post.assert_not_called()

if __name__=='__main__':unittest.main()
