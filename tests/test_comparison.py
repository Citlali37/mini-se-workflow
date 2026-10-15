import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mini_se_workflow import comparison
from mini_se_workflow.store import RunStore


class ComparisonTests(unittest.TestCase):
    def test_contract_failure_uses_the_fixed_development_denominator(self):
        from mini_se_workflow.demo import DemoClient, DEMO_TASK, benchmark_cases
        from mini_se_workflow.workflow import MiniSEWorkflow
        class Client(DemoClient):
            def complete_json(self, **kwargs):
                if kwargs['agent_name'] == 'coding':
                    return {'summary': 'incomplete', 'files': {}}
                return super().complete_json(**kwargs)
        with tempfile.TemporaryDirectory() as temp:
            runner = comparison.DevelopmentRunner(benchmark_cases()[:1])
            state = MiniSEWorkflow(Client(), RunStore(temp), mode='demo', runner=runner, max_repairs=0).run(DEMO_TASK)
        self.assertEqual(state.status, 'failed_validation')
        self.assertEqual(state.iterations[0]['validation']['total'], 1)
        self.assertFalse(state.iterations[0]['validation']['cases'])

    def test_order_is_counterbalanced_and_all_trials_counted(self):
        items = [{'id':'a'},{'id':'b'},{'id':'c'}]
        order = comparison.schedule(items, 2)
        self.assertEqual(len(order), 12)
        for index in range(3):
            first = [arm for repeat,item,arm in order if repeat==0 and item['id']==items[index]['id']]
            second = [arm for repeat,item,arm in order if repeat==1 and item['id']==items[index]['id']]
            self.assertEqual(first, list(reversed(second)))

    def test_holdout_is_not_sent_to_either_agent_or_used_for_repair(self):
        item = next(c for c in json.loads(comparison.SUITE.read_text(encoding='utf-8')) if c['id']=='text-stats')
        item['holdout'][0]['description'] = 'HOLDOUT_NEVER_IN_PROMPT'
        class Client(comparison.ComparisonFixtureClient):
            def __init__(self):
                super().__init__()
                self.prompts=[]
            def complete_json(self, **kwargs):
                self.prompts.append(kwargs['system_prompt']+kwargs['user_prompt'])
                result=super().complete_json(**kwargs)
                if kwargs['agent_name']=='single_agent':
                    result['files']['main.py']=result['files']['main.py'].replace("'characters':len(t)","'characters':len(t) or 99")
                return result
        client=Client()
        with tempfile.TemporaryDirectory() as temp:
            suite=Path(temp)/'suite.json'
            suite.write_text(json.dumps([item],ensure_ascii=False),encoding='utf-8')
            with patch.object(comparison,'SUITE',suite):
                report=comparison.compare(client,RunStore(Path(temp)/'runs'),mode='comparison-fixture',repeats=1)
        single=next(r for r in report['trials'] if r['arm']=='single')
        multi=next(r for r in report['trials'] if r['arm']=='multi')
        self.assertEqual(single['status'],'approved')
        self.assertFalse(single['success'])
        self.assertEqual(single['repair_count'],0)
        self.assertTrue(multi['success'])
        self.assertEqual(single['logical_calls'],1)
        self.assertEqual(multi['logical_calls'],3)
        self.assertNotIn('HOLDOUT_NEVER_IN_PROMPT',''.join(client.prompts))
        self.assertEqual(report['metrics']['single']['trials'],1)
        self.assertEqual(report['metrics']['single']['success_rate'],0)

    def test_same_development_suite_overrides_model_authored_tests(self):
        runner=comparison.DevelopmentRunner([{'id':'DEV','description':'固定开发条件',
            'steps':[{'input':{},'expected':{'ok':True}}]}])
        result=runner.run({'main.py':'print("{\\"ok\\":false}")'},
            [{'id':'LOOSE','description':'模型放宽','steps':[{'input':{},'expected':{'ok':False}}]}])
        self.assertFalse(result['passed'])
        self.assertEqual(result['cases'][0]['id'],'DEV')


if __name__=='__main__':
    unittest.main()
