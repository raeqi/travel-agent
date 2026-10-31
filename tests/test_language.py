import io
import json
import unittest
from unittest.mock import patch
import language

class LanguageTests(unittest.TestCase):
    def response(self, intent):
        return io.BytesIO(json.dumps({'message':{'content':json.dumps(intent)}}).encode())
    def test_unknown_place_rejected(self):
        with patch.dict('os.environ',{'WANDER_MODEL':'test'}),patch('language.urlopen',return_value=self.response({'intent':'feedback','place_id':9,'kind':'visited'})):
            with self.assertRaises(ValueError):language.parse_intent('去过了',[{'id':1,'name':'书店'}])
    def test_feedback_preserves_user_evidence(self):
        with patch.dict('os.environ',{'WANDER_MODEL':'test'}),patch('language.urlopen',return_value=self.response({'intent':'feedback','place_id':1,'kind':'visited','text':'喜欢书店'})):
            result=language.parse_intent('陪朋友去过，不代表喜欢',[{'id':1,'name':'书店'}])
            self.assertEqual(result['text'],'陪朋友去过，不代表喜欢')
