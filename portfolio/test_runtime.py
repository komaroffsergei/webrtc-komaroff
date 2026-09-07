import asyncio
import unittest
from portfolio.runtime import DemoRuntime

class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_echo_uses_original_graph(self):
        result=await DemoRuntime().run('эхо Привет')
        self.assertEqual(result['text'],'Привет')
        self.assertEqual(result['status'],'DONE')
        self.assertEqual(result['events'],[])

    async def test_mock_io_and_timeout(self):
        runtime=DemoRuntime()
        result=await runtime.run('Привет')
        self.assertIn('Демонстрационный ответ',result['text'])
        self.assertEqual([x['mode'] for x in result['events']],['routing_decision','final_response'])
        with self.assertRaises(asyncio.TimeoutError):await runtime.run('таймаут')
        self.assertEqual((await runtime.run('эхо Повтор'))['text'],'Повтор')

if __name__=='__main__':unittest.main()
