import test from 'node:test';
import assert from 'node:assert/strict';
import {dashboardRefreshUrl} from '../src/dashboardRefresh.ts';

test('successful update navigates to fresh versioned HTML without losing the current setup route',()=>{
  const next=new URL(dashboardRefreshUrl('http://127.0.0.1:8742/?setup=device&theme=hearth#software','0.2.11',1234));
  assert.equal(next.origin,'http://127.0.0.1:8742');
  assert.equal(next.pathname,'/');
  assert.equal(next.searchParams.get('setup'),'device');
  assert.equal(next.searchParams.get('theme'),'hearth');
  assert.equal(next.hash,'#software');
  assert.equal(next.searchParams.get('ui_release'),'0.2.11');
  assert.equal(next.searchParams.get('ui_refresh'),'1234');
});

test('repeated recoveries replace the cache key instead of accumulating query parameters',()=>{
  const first=dashboardRefreshUrl('http://127.0.0.1:8742/?setup=google','0.2.11',10);
  const second=dashboardRefreshUrl(first,undefined,20);
  const next=new URL(second);
  assert.notEqual(second,first);
  assert.deepEqual(next.searchParams.getAll('ui_refresh'),['20']);
  assert.deepEqual(next.searchParams.getAll('ui_release'),['0.2.11']);
  assert.equal(next.searchParams.get('setup'),'google');
});

test('manual page refresh preserves preview parameters and an existing subpath',()=>{
  const next=new URL(dashboardRefreshUrl('http://localhost:5173/dashboard?demo=1&theme=neon-grid&setup=google',undefined,99));
  assert.equal(next.pathname,'/dashboard');
  assert.equal(next.searchParams.get('demo'),'1');
  assert.equal(next.searchParams.get('theme'),'neon-grid');
  assert.equal(next.searchParams.has('ui_release'),false);
});
