"""CPU-only async ownership fixtures; no native inference or Hub registration."""
import asyncio
import contextvars
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from hub_runtime import api
from ttd_model_runtime.protocol import HubError

marker=contextvars.ContextVar('fixture_request')

class RuntimeFixture:
    def __init__(self):self.completed=[]
    def complete_background_work(self):self.completed.append(marker.get(None))

class BackgroundOwnership(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory=tempfile.TemporaryDirectory();self.data=Path(self.directory.name)
        self.data_patch=patch.object(api,'DATA',self.data);self.data_patch.start()
        self.runtime=RuntimeFixture();api.build_api(self.runtime)
        self.job='cv-'+'0'*32
        self.batch=self.data/'batches'/self.job/'batch.json'
        api.write(self.batch,{'id':self.job,'status':'running','jobs':[self.job]})
        api.write(self.data/'jobs'/self.job/'job.json',{'id':self.job,'status':'uploaded'})
        api.active=True

    async def asyncTearDown(self):
        self.data_patch.stop();self.directory.cleanup()

    async def test_success_finishes_in_original_request_context(self):
        marker.set('request-a')
        def complete(path,log):
            self.assertEqual(marker.get(),'request-a')
            job=api.load('jobs',self.job)[1];job['status']='succeeded';api.write(path,job)
        with patch.object(api,'run_native',complete):await api.run(self.batch)
        self.assertEqual(api.load('batches',self.job)[1]['status'],'succeeded')
        self.assertEqual(self.runtime.completed,['request-a'])
        self.assertFalse(api.active)

    async def test_unknown_retains_unresolved_owner_and_cannot_be_replayed(self):
        def uncertain(path,log):raise HubError('execution_unknown')
        with patch.object(api,'run_native',uncertain):await api.run(self.batch)
        self.assertEqual(api.load('batches',self.job)[1]['status'],'unknown')
        self.assertEqual(api.load('jobs',self.job)[1]['status'],'unknown')
        self.assertEqual(self.runtime.completed,[])
        called=[]
        with patch.object(api,'run_native',lambda *args:called.append(args)):
            await api.run(self.batch)
        self.assertFalse(called)
        self.assertEqual(self.runtime.completed,[])
        self.assertEqual(api.load('batches',self.job)[1]['status'],'unknown')
